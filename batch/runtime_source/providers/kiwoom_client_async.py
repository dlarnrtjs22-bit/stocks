"""키움 REST API async 클라이언트 (httpx + 세마포어 기반 병렬화).

# Design Ref: Design §2.1 Layer 1 + §5.1 — Phase H 배치 성능 재작성
# Plan SC: 15:30 run 90초 / 19:30 재평가 15초 달성

기존 `kiwoom_client.KiwoomRESTClient`와의 관계:
- 토큰 관리(50분 TTL) 공유: 기존 동기 클라이언트에서 access_token()을 가져온다
- 인증 헤더 포맷은 동일
- Rate Limit 전략: 세마포어(N=8)로 동시 요청 수 제한 (너무 공격적이면 429)
- 전역 min_interval_sec 대신 per-request 대기 지움 — 서버측 Rate Limit은 429 재시도로 대응

사용 예:
    async with AsyncKiwoomClient() as client:
        tasks = [client.request("/api/dostk/chart", "ka10080", {"stk_cd": "005930_NX", ...})
                 for code in codes]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from providers.kiwoom_client import KiwoomAPIError, KiwoomRESTClient, KiwoomResponse, _resolved_urls
from providers.cache import QUOTE_CACHE, META_CACHE


logger = logging.getLogger(__name__)


DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT_SEC = 30.0
DEFAULT_MAX_RETRIES = 5


@dataclass
class AsyncClientStats:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    rate_limited: int = 0
    cache_hits: int = 0
    elapsed_sec: float = 0.0

    def as_dict(self) -> dict[str, float | int]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "rate_limited": self.rate_limited,
            "cache_hits": self.cache_hits,
            "elapsed_sec": round(self.elapsed_sec, 3),
            "qps": round(self.succeeded / self.elapsed_sec, 2) if self.elapsed_sec > 0 else 0.0,
        }


class AsyncKiwoomClient:
    """asyncio + httpx + 세마포어 기반 병렬 키움 REST 클라이언트."""

    def __init__(
        self,
        *,
        concurrency: int = DEFAULT_CONCURRENCY,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sync_client: KiwoomRESTClient | None = None,
    ) -> None:
        self._sync = sync_client or KiwoomRESTClient()
        self._concurrency = int(concurrency)
        self._timeout = float(timeout_sec)
        self._max_retries = int(max_retries)
        self._semaphore: asyncio.Semaphore | None = None
        self._client: httpx.AsyncClient | None = None
        self.stats = AsyncClientStats()

    async def __aenter__(self) -> "AsyncKiwoomClient":
        rest_base, _ = _resolved_urls()
        self._client = httpx.AsyncClient(
            base_url=rest_base,
            timeout=self._timeout,
            limits=httpx.Limits(
                max_connections=self._concurrency * 2,
                max_keepalive_connections=self._concurrency,
            ),
        )
        self._semaphore = asyncio.Semaphore(self._concurrency)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._semaphore = None

    async def request(
        self,
        path: str,
        api_id: str,
        payload: dict[str, Any],
        *,
        cont_yn: str = "N",
        next_key: str = "",
        cache_key: str | None = None,
        cache_ttl_sec: float | None = None,
    ) -> KiwoomResponse:
        """단일 요청. cache_key 주어지면 QUOTE_CACHE에서 먼저 조회."""
        if self._client is None or self._semaphore is None:
            raise RuntimeError("AsyncKiwoomClient must be used as async context manager")

        if cache_key:
            cached = QUOTE_CACHE.get(cache_key)
            if cached is not None:
                self.stats.cache_hits += 1
                return cached  # type: ignore[return-value]

        token = self._sync.access_token()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": api_id,
        }

        async with self._semaphore:
            return await self._send_with_retry(path, api_id, payload, headers, cache_key, cache_ttl_sec)

    async def _send_with_retry(
        self,
        path: str,
        api_id: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        cache_key: str | None,
        cache_ttl_sec: float | None,
    ) -> KiwoomResponse:
        assert self._client is not None
        self.stats.total += 1
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = await self._client.post(path, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = KiwoomAPIError(f"transport error: {exc}")
                await asyncio.sleep(0.25 * (2 ** attempt))
                continue

            if response.status_code == 429:
                self.stats.rate_limited += 1
                retry_after = response.headers.get("retry-after")
                wait = float(retry_after) if retry_after else 0.25 * (2 ** attempt)
                await asyncio.sleep(max(wait, 0.1))
                last_error = KiwoomAPIError(f"rate limited: {api_id}")
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                last_error = KiwoomAPIError(f"http {response.status_code}: {exc}")
                await asyncio.sleep(0.25 * (2 ** attempt))
                continue

            body = response.json()
            return_code = body.get("return_code")
            if return_code is not None and str(return_code).strip() not in {"", "0"}:
                message = str(body.get("return_msg", "") or response.text[:200])
                # return_code 가 rate limit류이면 재시도
                if "LIMIT" in message.upper() or "RATE" in message.upper():
                    self.stats.rate_limited += 1
                    await asyncio.sleep(0.25 * (2 ** attempt))
                    last_error = KiwoomAPIError(message)
                    continue
                self.stats.failed += 1
                raise KiwoomAPIError(message)

            response_headers = {k.lower(): v for k, v in response.headers.items()}
            result = KiwoomResponse(body=body, headers=response_headers)
            if cache_key:
                QUOTE_CACHE.set(cache_key, result, ttl_sec=cache_ttl_sec)
            self.stats.succeeded += 1
            return result

        self.stats.failed += 1
        raise last_error or KiwoomAPIError(f"kiwoom request failed after retries: {api_id}")

    async def gather(
        self,
        requests: list[tuple[str, str, dict[str, Any]]],
        *,
        cache_key_fn: Any = None,
        cache_ttl_sec: float | None = None,
    ) -> list[KiwoomResponse | Exception]:
        """다수 요청을 병렬 실행. (path, api_id, payload) 튜플 리스트를 받음.

        cache_key_fn: (path, api_id, payload) -> str|None 를 반환하는 callable
        """
        start = time.time()

        async def _one(path: str, api_id: str, payload: dict[str, Any]):
            key = cache_key_fn(path, api_id, payload) if cache_key_fn else None
            return await self.request(path, api_id, payload, cache_key=key, cache_ttl_sec=cache_ttl_sec)

        tasks = [_one(p, a, pl) for (p, a, pl) in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self.stats.elapsed_sec = time.time() - start
        return results

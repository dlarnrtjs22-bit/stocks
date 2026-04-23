from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import websockets


REST_BASE_URL_REAL = "https://api.kiwoom.com"
REST_BASE_URL_MOCK = "https://mockapi.kiwoom.com"
WS_BASE_URL_REAL = "wss://api.kiwoom.com:10000/api/dostk/websocket"
WS_BASE_URL_MOCK = "wss://mockapi.kiwoom.com:10000/api/dostk/websocket"
TOKEN_PATH = "/oauth2/token"
# 실전 계좌 키
APPKEY_FILE_REAL = "58416417_appkey.txt"
SECRETKEY_FILE_REAL = "58416417_secretkey.txt"
# 모의투자 계좌 키 (별도 키 발급 필요. 없으면 실전 키 fallback)
APPKEY_FILE_MOCK = "58416417_appkey_mock.txt"
SECRETKEY_FILE_MOCK = "58416417_secretkey_mock.txt"
# Backward compat
APPKEY_FILE_NAME = APPKEY_FILE_REAL
SECRETKEY_FILE_NAME = SECRETKEY_FILE_REAL

# .bkit/state/trading_mode 파일로 실전/모의 전환 (Design §5.7, Plan §9)
TRADING_MODE_FILE = Path(__file__).resolve().parents[3] / ".bkit" / "state" / "trading_mode"


def _resolve_trading_mode() -> str:
    """trading_mode 파일이 'mock' 이면 모의투자, 아니면 실전.
    우선순위: env KIWOOM_TRADING_MODE > state 파일 > default=real.
    """
    env = str(os.getenv("KIWOOM_TRADING_MODE", "") or "").strip().lower()
    if env in {"mock", "real"}:
        return env
    try:
        if TRADING_MODE_FILE.exists():
            content = TRADING_MODE_FILE.read_text(encoding="utf-8").strip().lower()
            if content == "mock":
                return "mock"
    except Exception:
        pass
    return "real"


def _resolved_urls() -> tuple[str, str]:
    """(REST_BASE_URL, WS_BASE_URL) — 모의투자면 mockapi, 아니면 실전."""
    if _resolve_trading_mode() == "mock":
        return REST_BASE_URL_MOCK, WS_BASE_URL_MOCK
    return REST_BASE_URL_REAL, WS_BASE_URL_REAL


# 기존 코드 호환: REST_BASE_URL / WS_BASE_URL 상수는 import 시점 기준으로 고정되지 않고
# 매 요청 때 _resolved_urls()를 다시 읽도록 KiwoomRESTClient를 수정한다.
REST_BASE_URL, WS_BASE_URL = _resolved_urls()


class KiwoomAPIError(RuntimeError):
    pass


@dataclass(slots=True)
class KiwoomResponse:
    body: dict[str, Any]
    headers: dict[str, str]


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def effective_venue(now_epoch: float | None = None) -> tuple[str, str]:
    ts = time.localtime(now_epoch or time.time())
    hhmm = ts.tm_hour * 100 + ts.tm_min
    if hhmm >= 1540:
        return "NXT", "2"
    return "KRX", "1"


def venue_stock_code(ticker: str, venue: str) -> str:
    base = str(ticker or "").strip().upper()
    if not base:
        return ""
    if venue == "NXT" and not base.endswith("_NX"):
        return f"{base}_NX"
    return base


class KiwoomRESTClient:
    def __init__(self) -> None:
        self._project_root = project_root()
        # 실전/모의 별도 키 관리 (trading_mode에 따라 access_token에서 선택)
        self._token_by_mode: dict[str, tuple[str, float]] = {}
        self._session = requests.Session()
        self._last_request_ts = 0.0
        self._min_interval_sec = 0.22
        self._max_retries = 5

    def _read_secret(self, file_name: str) -> str:
        path = self._project_root / file_name
        if not path.exists():
            raise KiwoomAPIError(f"{file_name} not found at {path}")
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            raise KiwoomAPIError(f"{file_name} is empty")
        return value

    def _credentials_for(self, mode: str) -> tuple[str, str]:
        """trading_mode='mock' 이면 모의투자 키, 없으면 실전 키 fallback."""
        if mode == "mock":
            try:
                appkey = self._read_secret(APPKEY_FILE_MOCK)
                secretkey = self._read_secret(SECRETKEY_FILE_MOCK)
                return appkey, secretkey
            except KiwoomAPIError:
                # 모의 키 미발급 상태 — 실전 키를 mockapi URL에 붙여 쓰면 401/403 예상
                # 실제로는 모의 키 발급 필요. 당장은 실전 키로 폴백해서 동작 흐름 유지.
                pass
        return (
            self._read_secret(APPKEY_FILE_REAL),
            self._read_secret(SECRETKEY_FILE_REAL),
        )

    def access_token(self) -> str:
        mode = _resolve_trading_mode()
        cached = self._token_by_mode.get(mode)
        if cached and time.time() < cached[1]:
            return cached[0]

        appkey, secretkey = self._credentials_for(mode)
        rest_base, _ = _resolved_urls()  # 실전/모의 런타임 선택
        response = self._session.post(
            f"{rest_base}{TOKEN_PATH}",
            json={
                "grant_type": "client_credentials",
                "appkey": appkey,
                "secretkey": secretkey,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        token = str(data.get("token", "")).strip()
        if not token:
            raise KiwoomAPIError(str(data.get("return_msg", "kiwoom token missing")))
        self._token_by_mode[mode] = (token, time.time() + 60 * 50)
        return token

    def request(self, path: str, api_id: str, payload: dict[str, Any], *, cont_yn: str = "N", next_key: str = "") -> KiwoomResponse:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self.access_token()}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": api_id,
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            sleep_for = self._min_interval_sec - (time.time() - self._last_request_ts)
            if sleep_for > 0:
                time.sleep(sleep_for)

            rest_base, _ = _resolved_urls()
            response = self._session.post(
                f"{rest_base}{path}",
                headers=headers,
                json=payload,
                timeout=30,
            )
            self._last_request_ts = time.time()

            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                wait_sec = float(retry_after) if retry_after else self._min_interval_sec * (2 ** attempt)
                time.sleep(max(wait_sec, self._min_interval_sec))
                last_error = KiwoomAPIError(f"rate limited: {api_id}")
                continue

            response.raise_for_status()
            body = response.json()
            return_code = body.get("return_code")
            if return_code is not None and str(return_code).strip() not in {"", "0"}:
                message = str(body.get("return_msg", "") or response.text[:200])
                raise KiwoomAPIError(message)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return KiwoomResponse(body=body, headers=response_headers)

        raise last_error or KiwoomAPIError(f"kiwoom request failed after retries: {api_id}")

    def paginate(self, path: str, api_id: str, payload: dict[str, Any], *, max_pages: int = 10) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        cont_yn = "N"
        next_key = ""
        for _ in range(max_pages):
            result = self.request(path, api_id, payload, cont_yn=cont_yn, next_key=next_key)
            pages.append(result.body)
            cont_yn = str(result.headers.get("cont-yn", "N") or "N").upper()
            next_key = str(result.headers.get("next-key", "") or "")
            if cont_yn != "Y" or not next_key:
                break
        return pages


class KiwoomWebSocketClient:
    def __init__(self, rest_client: KiwoomRESTClient | None = None) -> None:
        self._rest = rest_client or KiwoomRESTClient()

    async def request_once(self, payload: dict[str, Any], *, expect_trnm: str | None = None, timeout_sec: int = 15) -> dict[str, Any]:
        _, ws_base = _resolved_urls()
        async with websockets.connect(ws_base, max_size=2**22) as ws:
            await ws.send(json.dumps({"trnm": "LOGIN", "token": self._rest.access_token()}))
            login_response = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout_sec))
            if int(login_response.get("return_code", 1) or 1) != 0:
                raise KiwoomAPIError(str(login_response.get("return_msg", "websocket login failed")))

            await ws.send(json.dumps(payload))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout_sec))
                if message.get("trnm") == "LOGIN":
                    continue
                if expect_trnm and message.get("trnm") not in {expect_trnm, "REAL"}:
                    continue
                return message

    def request(self, payload: dict[str, Any], *, expect_trnm: str | None = None, timeout_sec: int = 15) -> dict[str, Any]:
        return asyncio.run(self.request_once(payload, expect_trnm=expect_trnm, timeout_sec=timeout_sec))

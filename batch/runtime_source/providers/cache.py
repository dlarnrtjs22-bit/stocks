"""TTL 딕셔너리 캐시 - Redis 없는 in-memory 캐시.

# Design Ref: Design §2.1 Layer 1 - Phase H 배치 성능 재작성의 캐시 레이어
# Plan SC: 15:30 run 90초 / 19:30 재평가 15초 달성을 위한 동일 종목 중복 조회 방지

사용처:
- 1회 run 내 동일 종목 2회 이상 조회 방지
- 장 마감 후 변하지 않는 메타데이터 TTL 캐시
- 뉴스 응답 등 일정 시간 재사용 가능한 응답
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar


T = TypeVar("T")


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float
    created_at: float = field(default_factory=time.time)


class TTLCache:
    """스레드 안전 TTL 딕셔너리 캐시.

    - 기본 TTL 60초
    - 만료된 엔트리는 get 시점에 lazy eviction
    - 명시적 clear / invalidate / size 지원
    """

    def __init__(self, default_ttl_sec: float = 60.0) -> None:
        self._store: dict[str, _Entry[Any]] = {}
        self._lock = threading.RLock()
        self.default_ttl_sec = float(default_ttl_sec)
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at <= now:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_sec: float | None = None) -> None:
        ttl = float(ttl_sec) if ttl_sec is not None else self.default_ttl_sec
        expires = time.time() + ttl
        with self._lock:
            self._store[key] = _Entry(value=value, expires_at=expires)

    def get_or_compute(self, key: str, fn: Callable[[], T], ttl_sec: float | None = None) -> T:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = fn()
        self.set(key, value, ttl_sec)
        return value

    async def get_or_compute_async(self, key: str, afn: Callable[[], Any], ttl_sec: float | None = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = await afn()
        self.set(key, value, ttl_sec)
        return value

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }

    def evict_expired(self) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            keys = [k for k, e in self._store.items() if e.expires_at <= now]
            for k in keys:
                del self._store[k]
                removed += 1
        return removed


# 프로젝트 공용 싱글톤들 — TTL 축별로 분리
QUOTE_CACHE = TTLCache(default_ttl_sec=3.0)        # 실시간 시세는 짧게
META_CACHE = TTLCache(default_ttl_sec=3600.0)      # 종목 메타는 1시간
NEWS_CACHE = TTLCache(default_ttl_sec=300.0)       # 뉴스는 5분
UNIVERSE_CACHE = TTLCache(default_ttl_sec=86400.0) # 유니버스는 하루

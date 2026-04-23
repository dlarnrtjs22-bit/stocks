"""NXT 거래 가능 종목 조회 서비스.

# Design Ref: Design §2.2 Module A - CSV 기반 lookup + TTL 캐시
# Plan SC: featured 카드에 NXT 배지 즉시 표시, 7일 이상 미갱신 시 UI 회색 처리

CSV: data/nxt_tickers.csv
동작: 파일 mtime 기준 자동 리로드 + 싱글톤.
"""
from __future__ import annotations

import csv
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CSV_PATH = _PROJECT_ROOT / "data" / "nxt_tickers.csv"

# 7일 이상 미갱신이면 stale. UI에서 배지를 회색 처리하거나 경고 표시용.
STALE_THRESHOLD_DAYS = 7

_FIELDNAMES = ("stock_code", "market", "name", "tier", "source_rev")


@dataclass
class NxtEligibility:
    eligible: bool
    market: str | None = None
    name: str | None = None
    tier: int | None = None
    source_rev: str | None = None


@dataclass
class NxtRegistry:
    entries: dict[str, NxtEligibility] = field(default_factory=dict)
    file_mtime: float = 0.0
    loaded_at: datetime | None = None
    stale: bool = False

    def size(self) -> int:
        return len(self.entries)


class NxtLookupService:
    def __init__(self, csv_path: Path | None = None) -> None:
        self._csv_path = csv_path or _CSV_PATH
        self._registry = NxtRegistry()
        self._lock = threading.RLock()

    def _needs_reload(self) -> bool:
        try:
            mtime = self._csv_path.stat().st_mtime
        except FileNotFoundError:
            return self._registry.size() > 0  # 파일 사라짐 = 리셋
        return mtime != self._registry.file_mtime

    def _reload(self) -> None:
        if not self._csv_path.exists():
            logger.warning("nxt_tickers.csv not found at %s", self._csv_path)
            self._registry = NxtRegistry(stale=True, loaded_at=datetime.now(timezone.utc))
            return

        entries: dict[str, NxtEligibility] = {}
        try:
            with self._csv_path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(_strip_comments(f), fieldnames=list(_FIELDNAMES))
                for row in reader:
                    code = str(row.get("stock_code", "")).strip()
                    if not code or not code.isdigit():
                        continue
                    tier_raw = str(row.get("tier", "1")).strip()
                    try:
                        tier = int(tier_raw)
                    except ValueError:
                        tier = 1
                    entries[code.zfill(6)] = NxtEligibility(
                        eligible=(tier >= 1),
                        market=str(row.get("market", "")).strip() or None,
                        name=str(row.get("name", "")).strip() or None,
                        tier=tier,
                        source_rev=str(row.get("source_rev", "")).strip() or None,
                    )
        except Exception as exc:
            logger.exception("failed to load nxt_tickers.csv: %s", exc)
            return

        mtime = self._csv_path.stat().st_mtime
        now = datetime.now(timezone.utc)
        stale = _is_stale(mtime, now)
        self._registry = NxtRegistry(
            entries=entries,
            file_mtime=mtime,
            loaded_at=now,
            stale=stale,
        )
        logger.info(
            "nxt_lookup reloaded: %d entries, mtime=%s, stale=%s",
            len(entries),
            datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
            stale,
        )

    def is_eligible(self, stock_code: str) -> bool:
        entry = self.get(stock_code)
        return entry.eligible if entry else False

    def get(self, stock_code: str) -> NxtEligibility | None:
        code = str(stock_code or "").strip().zfill(6) if stock_code else ""
        if not code:
            return None
        with self._lock:
            if self._needs_reload():
                self._reload()
            return self._registry.entries.get(code)

    def stats(self) -> dict[str, object]:
        with self._lock:
            if self._needs_reload():
                self._reload()
            reg = self._registry
            return {
                "entries": reg.size(),
                "file_mtime": reg.file_mtime,
                "loaded_at": reg.loaded_at.isoformat() if reg.loaded_at else None,
                "stale": reg.stale,
            }


def _strip_comments(lines: Iterator[str]) -> Iterator[str]:
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        yield line


def _is_stale(mtime: float, now: datetime) -> bool:
    if mtime <= 0:
        return True
    mtime_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    delta = now - mtime_dt
    return delta.days >= STALE_THRESHOLD_DAYS


_singleton_lock = threading.Lock()
_singleton: NxtLookupService | None = None


def get_nxt_lookup() -> NxtLookupService:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = NxtLookupService()
    return _singleton


def recommended_plan(eligible: bool) -> tuple[str | None, str | None]:
    """NXT 가능 여부에 따라 (recommended_window, recommended_order_type) 반환.

    # Design Ref: Design §6.2 TO-BE - C 우선 + A 보조 투트랙
    """
    if eligible:
        return ("19:40-19:55", "LIMIT")
    return ("15:22-15:28", "LIMIT")

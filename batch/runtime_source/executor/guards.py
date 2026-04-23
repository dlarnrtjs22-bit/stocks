"""Module G: 자동매매 안전장치 (4축).

# Design Ref: Design §5.7 + §9 — kill switch, daily -5% limit, paper mode, consecutive fail
# Plan §9 안전장치 4축 (Slack 알림은 alerts.py에서 담당)

모든 주문 발주 직전 check_allowed() 호출 → GuardDecision 반환.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATE_DIR = PROJECT_ROOT / ".bkit" / "state"
KILL_SWITCH_PATH = STATE_DIR / "auto_trade_enabled"
PAPER_MODE_PATH = STATE_DIR / "paper_mode"
FAIL_COUNTER_PATH = STATE_DIR / "consecutive_fail_count"

DAILY_LOSS_LIMIT_PCT = -5.0
CONSECUTIVE_FAIL_LIMIT = 3


@dataclass
class GuardDecision:
    allowed: bool = True
    paper: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "paper": self.paper, "reason": self.reason}


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _read_file_int(path: Path, default: int = 0) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return default


def _kill_switch_enabled() -> bool:
    _ensure_state_dir()
    if not KILL_SWITCH_PATH.exists():
        return False  # 기본: 비활성 (안전 우선)
    return KILL_SWITCH_PATH.read_text(encoding="utf-8").strip() == "1"


def _paper_mode_on() -> bool:
    _ensure_state_dir()
    if not PAPER_MODE_PATH.exists():
        return False
    return PAPER_MODE_PATH.read_text(encoding="utf-8").strip() == "1"


def _daily_loss_exceeded() -> bool:
    try:
        from backend.app.core.database import db_connection
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Asia/Seoul")).date()
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cumulative_pct FROM daily_pnl WHERE pnl_date = %s",
                    (today,),
                )
                row = cur.fetchone()
                if not row:
                    return False
                cum = float(row.get("cumulative_pct", 0) or 0)
                return cum <= DAILY_LOSS_LIMIT_PCT
    except Exception:
        return False


def _consecutive_failures() -> int:
    return _read_file_int(FAIL_COUNTER_PATH, 0)


def increment_failure() -> int:
    _ensure_state_dir()
    n = _consecutive_failures() + 1
    FAIL_COUNTER_PATH.write_text(str(n), encoding="utf-8")
    if n >= CONSECUTIVE_FAIL_LIMIT:
        PAPER_MODE_PATH.write_text("1", encoding="utf-8")
    return n


def reset_failures() -> None:
    _ensure_state_dir()
    FAIL_COUNTER_PATH.write_text("0", encoding="utf-8")


def enable_kill_switch() -> None:
    _ensure_state_dir()
    KILL_SWITCH_PATH.write_text("1", encoding="utf-8")


def disable_kill_switch() -> None:
    _ensure_state_dir()
    KILL_SWITCH_PATH.write_text("0", encoding="utf-8")


def check_allowed(action: str = "order", ctx: dict | None = None) -> GuardDecision:
    if not _kill_switch_enabled():
        return GuardDecision(allowed=False, reason="KILL_SWITCH_OFF")
    if action == "buy" and _daily_loss_exceeded():
        return GuardDecision(allowed=False, reason="DAILY_LOSS_LIMIT")
    if _consecutive_failures() >= CONSECUTIVE_FAIL_LIMIT:
        PAPER_MODE_PATH.write_text("1", encoding="utf-8")
        return GuardDecision(allowed=True, paper=True, reason="PAPER_MODE_AUTO")
    if _paper_mode_on():
        return GuardDecision(allowed=True, paper=True, reason="PAPER_MODE_MANUAL")
    return GuardDecision(allowed=True, paper=False)


def status() -> dict[str, Any]:
    return {
        "kill_switch_enabled": _kill_switch_enabled(),
        "paper_mode": _paper_mode_on(),
        "consecutive_failures": _consecutive_failures(),
        "daily_loss_exceeded": _daily_loss_exceeded(),
    }

"""자동매매 컨트롤 API.

# Design Ref: Design §5.7 + §9 Module G — kill switch / paper mode / trading mode
# Plan §9: 실시간 on/off UI

엔드포인트:
  GET  /api/controls/status                — 현재 상태
  POST /api/controls/killswitch            — 자동매매 on/off
  POST /api/controls/paper                 — paper mode on/off
  POST /api/controls/trading-mode          — 실전/모의 전환
  POST /api/controls/job/{job_name}        — 개별 job on/off (schedule_disabled_jobs)
  GET  /api/controls/candidates/top2       — 오늘의 Top 2 후보 (최신)
  GET  /api/controls/briefing              — 최신 장후 브리핑
  GET  /api/controls/orders/today          — 오늘 자동 주문 이력
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.core.database import db_connection


router = APIRouter(prefix="/api/controls", tags=["controls"])

SEOUL_TZ = ZoneInfo("Asia/Seoul")
STATE_DIR = settings.project_root / ".bkit" / "state"
KILL_SWITCH_PATH = STATE_DIR / "auto_trade_enabled"
PAPER_MODE_PATH = STATE_DIR / "paper_mode"
TRADING_MODE_PATH = STATE_DIR / "trading_mode"
DISABLED_JOBS_PATH = STATE_DIR / "disabled_jobs"  # 한 줄에 하나씩 job name
EXTRACT_STATUS_PATH = STATE_DIR / "last_extract_status.json"


class BoolToggleRequest(BaseModel):
    enabled: bool
    reason: str | None = None


class TradingModeRequest(BaseModel):
    mode: str  # "real" or "mock"
    reason: str | None = None


class JobToggleRequest(BaseModel):
    enabled: bool


def _read_flag(path: Path) -> bool:
    if not path.exists():
        return False
    return path.read_text(encoding="utf-8").strip() == "1"


def _write_flag(path: Path, enabled: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1" if enabled else "0", encoding="utf-8")


def _read_trading_mode() -> str:
    if not TRADING_MODE_PATH.exists():
        return "real"
    content = TRADING_MODE_PATH.read_text(encoding="utf-8").strip().lower()
    return "mock" if content == "mock" else "real"


def _write_trading_mode(mode: str) -> None:
    TRADING_MODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRADING_MODE_PATH.write_text("mock" if mode == "mock" else "real", encoding="utf-8")


def _read_disabled_jobs() -> set[str]:
    if not DISABLED_JOBS_PATH.exists():
        return set()
    return {line.strip() for line in DISABLED_JOBS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}


def _write_disabled_jobs(jobs: set[str]) -> None:
    DISABLED_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DISABLED_JOBS_PATH.write_text("\n".join(sorted(jobs)), encoding="utf-8")


JOB_NAMES = [
    "batches-run-all",  # 15:10 기존 8 배치 전체 실행 (LLM 포함)
    "extract",          # 15:30 Top 2 후보 추출 (LLM 재호출 X)
    "briefing-1930",    # 19:30 장후 브리핑 (2종목 LLM 재호출 포함 가능)
    "briefing-1940",    # 19:40 재평가
    "buy",              # 19:50 자동매수
    "sell",             # 08:00 자동매도
    "reconcile",        # 09:10 P/L 집계
    "refresh-nxt",      # 월요일 06:00 NXT 리스트 갱신
]


def _scheduler_alive() -> bool:
    """백엔드 내장 스케줄러 쓰레드가 살아있는지 확인."""
    import threading
    for t in threading.enumerate():
        if t.name == "stocks-scheduler" and t.is_alive():
            return True
    return False


def _read_extract_status() -> dict[str, Any] | None:
    """최근 15:30 extract 실행 결과 조회."""
    if not EXTRACT_STATUS_PATH.exists():
        return None
    try:
        import json as _json
        return _json.loads(EXTRACT_STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


@router.get("/status")
def get_control_status() -> dict[str, Any]:
    """현재 자동매매 전체 상태 조회."""
    disabled = _read_disabled_jobs()
    return {
        "kill_switch_enabled": _read_flag(KILL_SWITCH_PATH),
        "paper_mode": _read_flag(PAPER_MODE_PATH),
        "trading_mode": _read_trading_mode(),
        "scheduler_alive": _scheduler_alive(),
        "jobs": [
            {"name": name, "enabled": name not in disabled}
            for name in JOB_NAMES
        ],
        "last_extract_status": _read_extract_status(),
        "state_dir": str(STATE_DIR),
    }


@router.post("/killswitch")
def set_kill_switch(req: BoolToggleRequest) -> dict[str, Any]:
    _write_flag(KILL_SWITCH_PATH, req.enabled)
    # 전체 status 반환 (프론트에서 setStatus에 통째로 대입 가능)
    return get_control_status()


@router.post("/paper")
def set_paper_mode(req: BoolToggleRequest) -> dict[str, Any]:
    _write_flag(PAPER_MODE_PATH, req.enabled)
    return get_control_status()


@router.post("/trading-mode")
def set_trading_mode(req: TradingModeRequest) -> dict[str, Any]:
    mode = (req.mode or "").strip().lower()
    if mode not in {"real", "mock"}:
        raise HTTPException(status_code=400, detail="mode must be 'real' or 'mock'")
    _write_trading_mode(mode)
    return get_control_status()


@router.post("/job/{job_name}")
def toggle_job(job_name: str, req: JobToggleRequest) -> dict[str, Any]:
    if job_name not in JOB_NAMES:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_name}. valid: {JOB_NAMES}")
    disabled = _read_disabled_jobs()
    if req.enabled:
        disabled.discard(job_name)
    else:
        disabled.add(job_name)
    _write_disabled_jobs(disabled)
    return {
        "job_name": job_name,
        "enabled": job_name not in disabled,
        "all_disabled": sorted(disabled),
    }


@router.get("/candidates/top2")
def get_top2_candidates(date_arg: str | None = Query(None, alias="date")) -> dict[str, Any]:
    """오늘의 Top 2 후보 (최신 candidate_set_v3)."""
    target_date = date_arg or datetime.now(SEOUL_TZ).date().isoformat()
    candidates: list[dict[str, Any]] = []
    latest_ts: str | None = None
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT rank, stock_code, stock_name, sector, score_total,
                           base_grade, final_grade, change_pct, trading_value,
                           entry_price_hint, nxt_eligible, recommended_window,
                           created_at, snapshot_json
                    FROM candidate_set_v3
                    WHERE set_date = %s
                    ORDER BY created_at DESC, rank ASC
                    LIMIT 2
                """, (target_date,))
                for row in cur.fetchall():
                    if latest_ts is None:
                        latest_ts = row.get("created_at").isoformat() if row.get("created_at") else None
                    candidates.append({
                        "rank": row["rank"],
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "sector": row["sector"],
                        "score_total": row["score_total"],
                        "base_grade": row["base_grade"],
                        "final_grade": row["final_grade"],
                        "change_pct": float(row["change_pct"] or 0),
                        "trading_value": int(row["trading_value"] or 0),
                        "entry_price_hint": float(row["entry_price_hint"] or 0),
                        "nxt_eligible": bool(row["nxt_eligible"]),
                        "recommended_window": row["recommended_window"],
                        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                    })
    except Exception as exc:
        return {"date": target_date, "candidates": [], "error": str(exc)}
    return {"date": target_date, "created_at": latest_ts, "candidates": candidates}


@router.get("/briefing")
def get_latest_briefing(date_arg: str | None = Query(None, alias="date")) -> dict[str, Any]:
    target_date = date_arg or datetime.now(SEOUL_TZ).date().isoformat()
    briefings: list[dict[str, Any]] = []
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (stock_code, brief_time)
                      brief_time, stock_code, news_status, liquidity_status,
                      liquidity_score, divergence_pct, divergence_warn,
                      us_es_chg_pct, us_nq_chg_pct, us_risk_off, action
                    FROM post_close_briefing
                    WHERE brief_date = %s
                    ORDER BY stock_code, brief_time DESC
                """, (target_date,))
                for row in cur.fetchall():
                    briefings.append({
                        "brief_time": row["brief_time"].isoformat() if row.get("brief_time") else None,
                        "stock_code": row["stock_code"],
                        "news_status": row["news_status"],
                        "liquidity_status": row["liquidity_status"],
                        "liquidity_score": float(row["liquidity_score"] or 0),
                        "divergence_pct": float(row["divergence_pct"] or 0) if row.get("divergence_pct") is not None else None,
                        "divergence_warn": bool(row["divergence_warn"]),
                        "us_es_chg_pct": float(row["us_es_chg_pct"] or 0),
                        "us_nq_chg_pct": float(row["us_nq_chg_pct"] or 0),
                        "us_risk_off": bool(row["us_risk_off"]),
                        "action": row["action"],
                    })
    except Exception as exc:
        return {"date": target_date, "briefings": [], "error": str(exc)}
    return {"date": target_date, "briefings": briefings}


@router.get("/orders/today")
def get_today_orders(date_arg: str | None = Query(None, alias="date")) -> dict[str, Any]:
    target_date = date_arg or datetime.now(SEOUL_TZ).date().isoformat()
    orders: list[dict[str, Any]] = []
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT order_id, stock_code, side, tranche, venue, order_type,
                           price, qty, status, filled_qty, filled_avg_price,
                           requested_at, filled_at, paper_mode, error_msg
                    FROM auto_orders
                    WHERE set_date = %s
                    ORDER BY requested_at DESC
                    LIMIT 50
                """, (target_date,))
                for row in cur.fetchall():
                    orders.append({
                        "order_id": row["order_id"],
                        "stock_code": row["stock_code"],
                        "side": row["side"],
                        "tranche": row["tranche"],
                        "venue": row["venue"],
                        "order_type": row["order_type"],
                        "price": float(row["price"] or 0),
                        "qty": int(row["qty"] or 0),
                        "status": row["status"],
                        "filled_qty": int(row["filled_qty"] or 0),
                        "filled_avg_price": float(row["filled_avg_price"] or 0),
                        "requested_at": row["requested_at"].isoformat() if row.get("requested_at") else None,
                        "filled_at": row["filled_at"].isoformat() if row.get("filled_at") else None,
                        "paper_mode": bool(row["paper_mode"]),
                        "error_msg": row.get("error_msg"),
                    })
    except Exception as exc:
        return {"date": target_date, "orders": [], "error": str(exc)}
    return {"date": target_date, "orders": orders}

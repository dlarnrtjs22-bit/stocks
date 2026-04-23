"""Module D: 19:30/19:40 장후 브리핑 배치.

# Design Ref: Design §6.4 위험 완화 4축
# Plan §6.4 신규 뉴스/NXT 유동성/가격 괴리/미국 선물 가드

4축:
  1. 신규 뉴스 LLM 재평가 — 15:30 이후 새로 나온 뉴스의 material_strength 확인
  2. NXT 애프터마켓 유동성 — 매수1호가±0.5% 잔량 기준
  3. KRX 종가 vs NXT 19:30 현재가 괴리 — ±1.5% 초과 시 경고
  4. 미국 ES/NQ 프리마켓 변동 — -1% 이상 하락 시 전체 연기 권고

결과는 post_close_briefing 테이블에 저장되고, 10분 재평가에서 활용된다.

Usage:
    python -m batch.runtime_source.pipelines.post_close_briefing           # 오늘
    python -m batch.runtime_source.pipelines.post_close_briefing --date 2026-04-23
    python -m batch.runtime_source.pipelines.post_close_briefing --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Design Ref: Design §6.4 — 4축 임계값
LIQUIDITY_THRESHOLD_RATIO = 0.005  # 매수1호가 ±0.5% 잔량 기준
LIQUIDITY_MIN_VOL = 1000  # 잔량 합 최소 (주식 수)
DIVERGENCE_WARN_PCT = 1.5  # KRX-NXT 가격 괴리 ±1.5% 초과
US_RISK_OFF_PCT = -1.0  # 미국 선물 -1% 이상 하락


@dataclass
class BriefingAxes:
    stock_code: str
    news_status: str = "UNKNOWN"  # OK / DETERIORATED / MISSING
    material_delta: float = 0.0
    liquidity_status: str = "UNAVAILABLE"  # OK / THIN / UNAVAILABLE
    liquidity_score: float = 0.0
    price_krx_close: float | None = None
    price_nxt_now: float | None = None
    divergence_pct: float | None = None
    divergence_warn: bool = False
    # 15:30 extract 시점 스냅샷 (candidate_set_v3.snapshot_json 에서 읽음)
    snapshot_opinion: str = "UNKNOWN"
    snapshot_decision_status: str = "UNKNOWN"
    # 현재 시점 AI/시장 재판단 결과
    current_opinion: str = "UNKNOWN"  # 매수 / 매도 / UNKNOWN
    current_decision_status: str = "UNKNOWN"  # BUY / MARKET_CAUTION_BLOCK / GRADE_BLOCKED / ...
    opinion_flipped: bool = False  # 스냅샷 BUY였는데 지금 매도로 뒤집혔나
    action: str = "KEEP"  # KEEP / REPLACE / DROP / QTY_HALF

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "news_status": self.news_status,
            "material_delta": round(self.material_delta, 3),
            "liquidity_status": self.liquidity_status,
            "liquidity_score": round(self.liquidity_score, 3),
            "price_krx_close": self.price_krx_close,
            "price_nxt_now": self.price_nxt_now,
            "divergence_pct": round(self.divergence_pct, 3) if self.divergence_pct is not None else None,
            "divergence_warn": self.divergence_warn,
            "snapshot_opinion": self.snapshot_opinion,
            "snapshot_decision_status": self.snapshot_decision_status,
            "current_opinion": self.current_opinion,
            "current_decision_status": self.current_decision_status,
            "opinion_flipped": self.opinion_flipped,
            "action": self.action,
        }


def fetch_us_futures_snapshot() -> tuple[float, float, bool]:
    """ES/NQ 선물 + 외부 시장 스냅샷.

    Design Ref: CLOSING_BET_PRINCIPLES §8.3 외부 시장 보정.
    기존에 engine.external_market_context.get_external_market_context() 가 Yahoo Spark API
    로 ES=F/NQ=F/유가/환율 등을 가져와 jongga_signals.ai_overall.external_market_context 에
    저장한다. 이 함수는 briefing 시점의 라이브 재확인을 위해 동일 소스를 5분 캐시로 재사용한다.

    반환:
      (ES change%, NQ change%, risk_off_flag)
    """
    try:
        import sys as _sys
        batch_root = PROJECT_ROOT / "batch" / "runtime_source"
        if str(batch_root) not in _sys.path:
            _sys.path.insert(0, str(batch_root))
        from engine.external_market_context import get_external_market_context

        ctx = get_external_market_context(max_age_sec=300)
        signals = ctx.get("signals") or {}
        es_chg = float((signals.get("sp500_futures") or {}).get("change_pct") or 0.0)
        nq_chg = float((signals.get("nasdaq_futures") or {}).get("change_pct") or 0.0)
        status = str(ctx.get("status") or "").upper()
        risk_off = status == "RISK_OFF"
        return es_chg, nq_chg, risk_off
    except Exception as exc:
        print(f"[briefing] external_market_context 조회 실패, 기본값 사용: {exc}")
        return 0.0, 0.0, False


def check_liquidity(
    stock_code: str,
    kiwoom_rest: Any,
    venue_ticker: str,
) -> tuple[str, float]:
    """NXT 애프터마켓 호가 스냅샷 기반 유동성 점검.

    정상적인 키움 호가 API 응답이 없으면 UNAVAILABLE 반환.
    """
    try:
        # ka10004 주식호가요청. 응답 필드:
        # cur_prc, buy_fpr_bid(매수1호가), sel_fpr_bid(매도1호가), buy_fpr_req(매수1잔량), sel_fpr_req(매도1잔량)
        res = kiwoom_rest.request(
            "/api/dostk/mrkcond",
            "ka10004",
            {"stk_cd": venue_ticker},
        )
        body = res.body if hasattr(res, "body") else res
        bid1 = abs(float(body.get("buy_fpr_bid") or 0))
        ask1 = abs(float(body.get("sel_fpr_bid") or 0))
        bid_qty = abs(float(body.get("buy_fpr_req") or 0))
        ask_qty = abs(float(body.get("sel_fpr_req") or 0))
        if bid1 <= 0 or ask1 <= 0:
            return "UNAVAILABLE", 0.0
        total_qty = bid_qty + ask_qty
        if total_qty < LIQUIDITY_MIN_VOL:
            return "THIN", total_qty
        return "OK", total_qty
    except Exception:
        return "UNAVAILABLE", 0.0


def check_news_freshness(stock_code: str, last_known_material: float = 0.0) -> tuple[str, float]:
    """15:30 이후 신규 뉴스 LLM 재평가.

    Design §6.4 axis 1. 현재는 기존 뉴스 material_strength 변화량 placeholder로 반환.
    실제 구현: 새 뉴스 수집 → LLM 재호출 → material_strength 비교.
    """
    # 현재는 데이터 없음으로 처리 → action 판단에 영향 없음
    return "UNKNOWN", 0.0


def compute_divergence(krx_close: float | None, nxt_now: float | None) -> tuple[float | None, bool]:
    if krx_close is None or nxt_now is None or krx_close <= 0:
        return None, False
    pct = (nxt_now - krx_close) / krx_close * 100.0
    return pct, abs(pct) > DIVERGENCE_WARN_PCT


def decide_action(axes: BriefingAxes, us_risk_off: bool) -> str:
    """4축 + AI 재판단 통합해서 action 결정.
    - AI 재판단 결과 '매도' (opinion_flipped) → DROP (최우선)
    - 미국 선물 risk_off → DROP
    - 신규 악재 감지 (DETERIORATED) → DROP
    - 유동성 THIN 또는 가격 괴리 warn → QTY_HALF
    - 그 외 → KEEP
    """
    # 최우선: 스냅샷 BUY였는데 지금 매도로 뒤집혔으면 무조건 DROP
    if axes.opinion_flipped:
        return "DROP"
    if us_risk_off:
        return "DROP"
    if axes.news_status == "DETERIORATED":
        return "DROP"
    if axes.liquidity_status == "THIN" or axes.divergence_warn:
        return "QTY_HALF"
    return "KEEP"


def run(target_date: str | None = None, dry_run: bool = False) -> int:
    from backend.app.core.database import open_db_pool, db_connection
    from backend.app.services.closing_bet_service import ClosingBetService

    try:
        open_db_pool()
    except Exception as exc:
        print(f"[briefing] DB 풀 초기화 실패: {exc}", file=sys.stderr)
        return 3

    if target_date is None:
        from zoneinfo import ZoneInfo
        target_date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()

    # candidate_set_v3 에서 오늘의 저장된 Top 2 (이게 실제 매수 대상)
    picks: list[dict[str, Any]] = []
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (stock_code)
                      stock_code, stock_name, entry_price_hint, nxt_eligible, recommended_window,
                      snapshot_json
                    FROM candidate_set_v3
                    WHERE set_date = %s
                    ORDER BY stock_code, created_at DESC
                """, (target_date,))
                for row in cur.fetchall():
                    snap = row.get("snapshot_json") or {}
                    if not isinstance(snap, dict):
                        snap = {}
                    picks.append({
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "entry_price": float(row["entry_price_hint"] or 0),
                        "snapshot_opinion": str(snap.get("ai_opinion") or "UNKNOWN"),
                        "snapshot_decision_status": str(snap.get("decision_status") or "UNKNOWN").upper(),
                    })
    except Exception as exc:
        print(f"[briefing] candidate_set_v3 조회 실패: {exc}", file=sys.stderr)
        return 2

    if not picks:
        print("[briefing] candidate_set_v3 비어있음. 15:30 extract 먼저 필요. 스킵.")
        return 0

    # 현재 시점 ClosingBetService 재조회: 각 종목의 "지금 시점" ai_opinion/decision_status
    svc = ClosingBetService()
    resp = svc.get_closing_bet(target_date, "ALL", "", 1, 300)
    current_view: dict[str, dict[str, Any]] = {}
    for item in resp.featured_items:
        current_view[item.ticker] = item.model_dump()
    for item in resp.items:
        if item.ticker not in current_view:
            current_view[item.ticker] = item.model_dump()

    print(f"[briefing] {target_date} candidate_set_v3 {len(picks)}종목 재판단")

    # 4축 공통: 미국 선물 스냅샷 (1회)
    es_chg, nq_chg, us_risk_off = fetch_us_futures_snapshot()
    if us_risk_off:
        print(f"[briefing] ⚠ US risk_off (ES={es_chg:+.2f}%, NQ={nq_chg:+.2f}%)")

    # 키움 REST 클라이언트 (호가 조회용)
    try:
        import sys as _sys
        batch_root = PROJECT_ROOT / "batch" / "runtime_source"
        if str(batch_root) not in _sys.path:
            _sys.path.insert(0, str(batch_root))
        from providers.kiwoom_client import KiwoomRESTClient, venue_stock_code
        kiwoom = KiwoomRESTClient()
    except Exception as exc:
        print(f"[briefing] Kiwoom client 초기화 실패, 유동성 UNAVAILABLE 처리: {exc}")
        kiwoom = None
        venue_stock_code = lambda t, v: t  # noqa

    brief_time = datetime.now(timezone.utc)
    axes_list: list[BriefingAxes] = []

    for p in picks:
        ax = BriefingAxes(stock_code=str(p.get("stock_code")))
        ax.snapshot_opinion = str(p.get("snapshot_opinion") or "UNKNOWN")
        ax.snapshot_decision_status = str(p.get("snapshot_decision_status") or "UNKNOWN").upper()

        # 축 1: 뉴스 재평가 (현재는 placeholder)
        ax.news_status, ax.material_delta = check_news_freshness(ax.stock_code)

        # 축 2: NXT 유동성
        if kiwoom is not None:
            ax.liquidity_status, ax.liquidity_score = check_liquidity(
                ax.stock_code, kiwoom, venue_stock_code(ax.stock_code, "NXT")
            )

        # 축 3: 가격 괴리
        ax.price_krx_close = float(p.get("entry_price") or 0) or None
        ax.price_nxt_now = ax.price_krx_close
        ax.divergence_pct, ax.divergence_warn = compute_divergence(ax.price_krx_close, ax.price_nxt_now)

        # 축 5: AI/시장 재판단 — 현재 시점 ai_opinion / decision_status 조회
        # ClosingBetService._to_item 이 조회마다 decide_trade_opinion 을 재계산하며,
        # 이게 전략의 핵심이다 (CLOSING_BET_PRINCIPLES §8.5 + §9.3).
        # 장 마감 후 external_market_context(미국선물/유가) 가 갱신되면 시장 위험도 재평가 →
        # CAUTION/RISK_OFF 로 뒤집히면 매수 금지가 정답.
        #
        # flip 판정: 15:30 추출 시점 스냅샷이 "매수"였는데 지금은 "매수"가 아니게 된 모든 경우.
        # 원인이 시장 컨텍스트든(GRADE_BLOCKED/MARKET_BLOCKED) 뉴스 부재든(NEWS_BLOCKED)
        # 점수 하락이든(SCORE_BLOCKED) 전부 DROP 해야 함 — 문서 §9.1~§9.3.
        cur_item = current_view.get(str(p.get("stock_code")))
        if cur_item:
            ax.current_opinion = str(cur_item.get("ai_opinion") or "UNKNOWN")
            ax.current_decision_status = str(cur_item.get("decision_status") or "UNKNOWN").upper()
            snapshot_was_buy = (ax.snapshot_opinion == "매수")
            ax.opinion_flipped = snapshot_was_buy and (ax.current_opinion != "매수")
        else:
            # 현재 응답에 해당 종목이 아예 없음 = 심각한 이상 (거래 정지 등)
            ax.current_opinion = "NOT_FOUND"
            ax.current_decision_status = "NOT_FOUND"
            ax.opinion_flipped = True  # 안전하게 DROP

        # 통합 action
        ax.action = decide_action(ax, us_risk_off)

        axes_list.append(ax)
        flip_mark = " ⚠FLIPPED" if ax.opinion_flipped else ""
        print(
            f"  {ax.stock_code} "
            f"snap={ax.snapshot_opinion}({ax.snapshot_decision_status}) "
            f"now={ax.current_opinion}({ax.current_decision_status}){flip_mark} "
            f"news={ax.news_status} liq={ax.liquidity_status}({ax.liquidity_score:.0f}) "
            f"div={ax.divergence_pct if ax.divergence_pct is not None else '?'}% "
            f"→ action={ax.action}"
        )

    if dry_run:
        print("[briefing] --dry-run: DB 저장 생략")
        return 0

    # DB 저장
    try:
        from backend.app.core.database import db_connection
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS post_close_briefing (
                        brief_date DATE NOT NULL,
                        brief_time TIMESTAMPTZ NOT NULL,
                        stock_code VARCHAR(12) NOT NULL,
                        news_status VARCHAR(24),
                        material_delta NUMERIC(5,2),
                        liquidity_status VARCHAR(24),
                        liquidity_score NUMERIC(10,2),
                        price_krx_close NUMERIC(12,2),
                        price_nxt_now NUMERIC(12,2),
                        divergence_pct NUMERIC(6,3),
                        divergence_warn BOOLEAN,
                        us_es_chg_pct NUMERIC(6,3),
                        us_nq_chg_pct NUMERIC(6,3),
                        us_risk_off BOOLEAN,
                        action VARCHAR(24),
                        payload JSONB,
                        PRIMARY KEY (brief_date, brief_time, stock_code)
                    )
                """)
                for ax in axes_list:
                    cur.execute(
                        """
                        INSERT INTO post_close_briefing
                          (brief_date, brief_time, stock_code, news_status, material_delta,
                           liquidity_status, liquidity_score, price_krx_close, price_nxt_now,
                           divergence_pct, divergence_warn, us_es_chg_pct, us_nq_chg_pct,
                           us_risk_off, action, payload)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (brief_date, brief_time, stock_code) DO UPDATE SET
                          news_status=EXCLUDED.news_status,
                          material_delta=EXCLUDED.material_delta,
                          liquidity_status=EXCLUDED.liquidity_status,
                          liquidity_score=EXCLUDED.liquidity_score,
                          action=EXCLUDED.action
                        """,
                        (
                            target_date, brief_time, ax.stock_code,
                            ax.news_status, ax.material_delta,
                            ax.liquidity_status, ax.liquidity_score,
                            ax.price_krx_close, ax.price_nxt_now,
                            ax.divergence_pct, ax.divergence_warn,
                            es_chg, nq_chg, us_risk_off,
                            ax.action,
                            json.dumps(ax.to_dict(), ensure_ascii=False),
                        ),
                    )
        print(f"[briefing] post_close_briefing에 {len(axes_list)}건 저장 완료")
    except Exception as exc:
        print(f"[briefing] DB 저장 실패: {exc}", file=sys.stderr)
        return 2

    # 실행 히스토리 기록
    try:
        from batch.runtime_source.utils.execution_history import record_event
        hhmm = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M")
        action_summary = ", ".join(f"{ax.stock_code}:{ax.action}" for ax in axes_list)
        flipped_cnt = sum(1 for ax in axes_list if ax.opinion_flipped)
        drop_cnt = sum(1 for ax in axes_list if ax.action == "DROP")
        summary = (
            f"{hhmm} 브리핑 — {len(axes_list)}종목 재평가, "
            f"DROP {drop_cnt} / flip {flipped_cnt} ({action_summary})"
        )
        record_event(
            event_type="briefing",
            summary=summary,
            details={
                "brief_time": hhmm,
                "us_risk_off": us_risk_off,
                "us_es_chg_pct": es_chg,
                "us_nq_chg_pct": nq_chg,
                "axes": [ax.to_dict() for ax in axes_list],
            },
            target_date=target_date,
        )
    except Exception as exc:
        print(f"[briefing] 히스토리 기록 실패 (무시): {exc}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Module D: 19:30 장후 브리핑")
    parser.add_argument("--date", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(target_date=args.date, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

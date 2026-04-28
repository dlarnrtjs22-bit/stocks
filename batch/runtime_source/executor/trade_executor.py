"""Module E+F: 자동매수/매도 상태기계.

# Design Ref: Design §5.4 + §5.5 + §7 + §8
# Plan §7 매수 tranche (19:50/54/58 40/30/30), §8 매도 스케줄 (08:00/02/04/05 단계적)

매수 플로우:
  19:50 T1 — 매수1호가+1틱(메이커) 40%
  19:54 T2 — 현재가(중립)        30%
  19:58 T3 — 매도1호가(테이커)   30%
  각 tranche 직전: guards.check_allowed(), Slack 통지 (선택)

매도 플로우 (익일):
  08:00 S0 — 현재가 50%
  08:02 S1 — 현재가 -1% 지정가 (잔량)
  08:04 S2 — 현재가 -2% 지정가 (잔량)
  08:05 S3 — 매수1호가 테이커
  08:06~08:49 — 1분마다 매수1호가 재조회·재발주
  08:50 — KRX 동시호가 이관
  09:00:30 — NXT 메인 시장가 IOC 최종
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from providers.kiwoom_order import (
    KiwoomOrderClient,
    OrderRequest,
    OrderResult,
    QuoteSnapshot,
    compute_buy_price,
    compute_sell_price,
)
from executor import guards
from executor.alerts import notify, wait_for_cancel


SEOUL_TZ = ZoneInfo("Asia/Seoul")
SELL_DEFENSE_DROP_PCT = -1.0
SELL_STRENGTH_CONFIRM_PCT = 1.0
SELL_RISING_CONFIRM_PCT = 0.5
SELL_TRAIL_PULLBACK_PCT = 0.8
SELL_TRAIL_PROFIT_FLOOR_PCT = 0.3


def _record_order_to_db(req: OrderRequest, result: OrderResult, tranche_name: str) -> None:
    """주문 발주 결과를 auto_orders 테이블에 기록.
    runner_sell, controls API, daily_pnl_reconcile 이 이 테이블을 읽는다.
    DB 실패는 주문 자체를 막지 않는다.
    """
    try:
        from backend.app.core.database import db_connection
        set_date_str = datetime.now(SEOUL_TZ).date().isoformat()
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auto_orders
                      (order_id, set_date, stock_code, side, tranche, venue, order_type,
                       price, qty, status, filled_qty, filled_avg_price, paper_mode,
                       error_msg, idempotency_key, note, requested_at,
                       filled_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW(),
                            CASE WHEN %s IN ('FILLED','PARTIAL') THEN NOW() ELSE NULL END)
                    ON CONFLICT (idempotency_key) DO UPDATE SET
                      status=EXCLUDED.status,
                      filled_qty=EXCLUDED.filled_qty,
                      filled_avg_price=EXCLUDED.filled_avg_price,
                      error_msg=EXCLUDED.error_msg,
                      filled_at=CASE WHEN EXCLUDED.status IN ('FILLED','PARTIAL')
                                     THEN COALESCE(auto_orders.filled_at, NOW())
                                     ELSE auto_orders.filled_at END
                    """,
                    (
                        result.order_id or f"NO_ID_{req.idempotency_key}",
                        set_date_str,
                        req.ticker, req.side, tranche_name,
                        req.venue, req.order_type,
                        req.price, req.qty, str(result.status or "PENDING"),
                        result.filled_qty, float(result.filled_avg_price or 0),
                        bool(result.paper_mode),
                        (result.error_msg or None),
                        req.idempotency_key,
                        req.note,
                        str(result.status or "PENDING"),
                    ),
                )
    except Exception as exc:
        print(f"[auto_orders INSERT 실패] {req.idempotency_key}: {exc}")


@dataclass
class BuyTrancheSpec:
    name: str
    hour: int
    minute: int
    ratio: float
    strategy: str  # MAKER_BID_PLUS_TICK / LAST / TAKER_ASK


# Design Ref: Design §5.4 — 메이커→중립→테이커 시간 경과 공격성 증가
BUY_TRANCHES = [
    BuyTrancheSpec("T1", 19, 50, 0.40, "MAKER_BID_PLUS_TICK"),
    BuyTrancheSpec("T2", 19, 54, 0.30, "LAST"),
    BuyTrancheSpec("T3", 19, 58, 0.30, "TAKER_ASK"),
]


@dataclass
class Candidate:
    stock_code: str
    name: str
    entry_hint: int  # 원화 (정수)
    action: str = "KEEP"  # Module D briefing 결과 (KEEP/QTY_HALF/DROP)
    sector: str = ""


@dataclass
class BuyPlan:
    candidate: Candidate
    total_qty: int
    tranche_qty: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stock_code": self.candidate.stock_code,
            "total_qty": self.total_qty,
            "tranche_qty": self.tranche_qty,
        }


def compute_allocation(
    deposit: int,
    candidates: list[Candidate],
    *,
    buffer_pct: float = 0.10,
) -> dict[str, BuyPlan]:
    """Design Ref: Design §5.6 — 200만원 예수금 + 몰빵 fallback"""
    if deposit <= 0 or not candidates:
        return {}

    usable = int(deposit * (1.0 - buffer_pct))

    # Module D 에서 QTY_HALF면 절반 축소
    effective_candidates: list[tuple[Candidate, float]] = []
    for c in candidates:
        if c.action == "DROP":
            continue
        weight = 0.5 if c.action == "QTY_HALF" else 1.0
        effective_candidates.append((c, weight))

    if not effective_candidates:
        return {}

    n = len(effective_candidates)
    total_weight = sum(w for _, w in effective_candidates)
    plans: dict[str, BuyPlan] = {}

    if n == 1:
        c, w = effective_candidates[0]
        alloc = int(usable * w / max(total_weight, 1e-6))
        qty = alloc // max(c.entry_hint, 1)
        if qty > 0:
            plans[c.stock_code] = BuyPlan(candidate=c, total_qty=qty)
    else:
        # 2종목: 가중치 배분
        for c, w in effective_candidates:
            alloc = int(usable * w / total_weight)
            qty = alloc // max(c.entry_hint, 1)
            if qty > 0:
                plans[c.stock_code] = BuyPlan(candidate=c, total_qty=qty)

    # "수량 0 → 1등 몰빵" fallback
    if not plans and effective_candidates:
        c, _ = effective_candidates[0]  # 우선순위 1등
        alloc = int(usable * 0.90)
        qty = alloc // max(c.entry_hint, 1)
        if qty > 0:
            plans[c.stock_code] = BuyPlan(candidate=c, total_qty=qty)

    # Tranche 분할 (40/30/30)
    for plan in plans.values():
        remaining = plan.total_qty
        for idx, t in enumerate(BUY_TRANCHES):
            if idx == len(BUY_TRANCHES) - 1:
                plan.tranche_qty[t.name] = remaining
            else:
                q = int(plan.total_qty * t.ratio)
                plan.tranche_qty[t.name] = q
                remaining -= q

    return plans


class TradeExecutor:
    """자동매매 주문 오케스트레이터."""

    def __init__(self, order_client: KiwoomOrderClient | None = None) -> None:
        self._client = order_client or KiwoomOrderClient()

    def _order_reserved_qty(self, result: OrderResult, requested_qty: int) -> int:
        status = str(result.status or "").upper()
        if status in {"FAILED", "CANCELLED", "CANCELED", "REJECTED"}:
            return 0
        filled_qty = int(result.filled_qty or 0)
        if filled_qty > 0:
            return min(int(requested_qty), filled_qty)
        return int(requested_qty)

    def _snapshot_price(self, snap: QuoteSnapshot) -> int:
        return int(snap.last or snap.bid1 or snap.midpoint() or 0)

    def _change_pct(self, price: int, reference: int) -> float | None:
        if price <= 0 or reference <= 0:
            return None
        return (price - reference) / reference * 100.0

    def _place_sell_and_reserve(
        self,
        results: list[OrderResult],
        stock_code: str,
        qty: int,
        price: int,
        tag: str,
        paper: bool,
        dry_run: bool,
    ) -> int:
        if qty <= 0 or price <= 0:
            return 0
        result = self._place_sell(stock_code, qty, price, tag, paper, dry_run)
        results.append(result)
        return self._order_reserved_qty(result, qty)

    # ─── 매수 ─────────────────────────────────────────
    def execute_buy_tranche(
        self,
        plan: BuyPlan,
        tranche: BuyTrancheSpec,
        *,
        dry_run: bool = False,
    ) -> OrderResult:
        decision = guards.check_allowed("buy", {"stock": plan.candidate.stock_code, "tranche": tranche.name})
        if not decision.allowed:
            notify(f":no_entry: BUY {plan.candidate.stock_code} {tranche.name} blocked: {decision.reason}")
            return OrderResult(status="FAILED", error_msg=decision.reason)

        qty = plan.tranche_qty.get(tranche.name, 0)
        if qty <= 0:
            return OrderResult(status="FAILED", error_msg="qty<=0")

        # 호가 스냅샷 → 지정가 계산
        snap = self._client.get_quote_snapshot(plan.candidate.stock_code, venue="NXT")
        price = compute_buy_price(snap, tranche.strategy)
        if price <= 0:
            notify(f":warning: BUY {plan.candidate.stock_code} {tranche.name}: price=0, skip")
            return OrderResult(status="FAILED", error_msg="price_resolve_fail")

        idem = f"BUY_{plan.candidate.stock_code}_{tranche.name}_{datetime.now(SEOUL_TZ).strftime('%Y%m%d')}"
        req = OrderRequest(
            ticker=plan.candidate.stock_code,
            side="BUY",
            qty=qty,
            price=price,
            venue="NXT",
            order_type="LIMIT_MAKER" if "MAKER" in tranche.strategy else "LIMIT_TAKER" if "TAKER" in tranche.strategy else "LIMIT",
            idempotency_key=idem,
            note=f"tranche={tranche.name} strategy={tranche.strategy}",
        )
        # Slack 알림 + 60초 취소 창 (paper_mode 아닐 때만)
        if not decision.paper and not dry_run:
            if not wait_for_cancel(f":robot: BUY {plan.candidate.stock_code} {tranche.name} qty={qty}@{price}", wait_sec=60):
                notify(f":white_check_mark: BUY {plan.candidate.stock_code} {tranche.name} user-cancelled")
                return OrderResult(status="CANCELLED", error_msg="user_cancel")

        result = self._client.place_limit_order(req, paper_mode=(decision.paper or dry_run))
        _record_order_to_db(req, result, tranche.name)
        return result

    def execute_buy_all_tranches(self, plans: list[BuyPlan], *, dry_run: bool = False, skip_wait: bool = False) -> list[OrderResult]:
        """19:50~19:58 모든 tranche 순차 실행 (시간 대기 포함).
        skip_wait=True 이면 시간 대기 없이 즉시 3개 tranche 연속 실행 (테스트용).
        """
        results: list[OrderResult] = []
        for tranche in BUY_TRANCHES:
            if not skip_wait:
                self._wait_until(tranche.hour, tranche.minute)
            for plan in plans:
                r = self.execute_buy_tranche(plan, tranche, dry_run=dry_run)
                results.append(r)
        return results

    # ─── 매도 ─────────────────────────────────────────
    def execute_sell_schedule(
        self,
        position_qty: int,
        stock_code: str,
        reference_close: int,
        *,
        dry_run: bool = False,
    ) -> list[OrderResult]:
        """Sell next-day positions with defensive and rising-open branches."""
        decision = guards.check_allowed("sell", {"stock": stock_code})
        if not decision.allowed:
            notify(f":no_entry: SELL {stock_code} blocked: {decision.reason}")
            return []

        return self._execute_adaptive_sell_schedule(
            position_qty=position_qty,
            stock_code=stock_code,
            reference_close=reference_close,
            paper=decision.paper,
            dry_run=dry_run,
        )

    def _execute_adaptive_sell_schedule(
        self,
        position_qty: int,
        stock_code: str,
        reference_close: int,
        *,
        paper: bool,
        dry_run: bool,
    ) -> list[OrderResult]:
        results: list[OrderResult] = []
        remaining = int(position_qty)
        if remaining <= 0:
            return results

        self._wait_until(8, 0)
        first_snap = self._client.get_quote_snapshot(stock_code, venue="NXT")
        first_price = self._snapshot_price(first_snap)
        first_change = self._change_pct(first_price, reference_close)
        if first_change is not None and first_change <= SELL_DEFENSE_DROP_PCT:
            price = compute_sell_price(first_snap, "BID1_TAKER")
            qty = remaining
            remaining -= self._place_sell_and_reserve(
                results, stock_code, qty, price, "S0-defense-drop", paper, dry_run
            )
            if remaining <= 0:
                return results

        self._wait_until(8, 2)
        second_snap = self._client.get_quote_snapshot(stock_code, venue="NXT")
        second_price = self._snapshot_price(second_snap)
        second_change = self._change_pct(second_price, reference_close)
        if second_change is not None and second_change <= SELL_DEFENSE_DROP_PCT:
            price = compute_sell_price(second_snap, "BID1_TAKER")
            qty = remaining
            remaining -= self._place_sell_and_reserve(
                results, stock_code, qty, price, "S0-defense-drop", paper, dry_run
            )
            if remaining <= 0:
                return results

        rising_from_reference = second_change is not None and second_change >= SELL_STRENGTH_CONFIRM_PCT
        rising_from_open = (
            first_price > 0
            and second_price > 0
            and second_price >= int(first_price * (1.0 + SELL_RISING_CONFIRM_PCT / 100.0))
        )
        if rising_from_reference or rising_from_open:
            remaining = self._execute_trailing_sell(
                results=results,
                stock_code=stock_code,
                remaining=remaining,
                reference_close=reference_close,
                high_price=max(first_price, second_price),
                paper=paper,
                dry_run=dry_run,
            )
        else:
            remaining = self._execute_staged_sell(
                results=results,
                stock_code=stock_code,
                remaining=remaining,
                first_sell_snap=second_snap,
                paper=paper,
                dry_run=dry_run,
            )

        self._wait_until(9, 0, 30)
        if remaining > 0:
            idem = f"SELL_IOC_{stock_code}_{datetime.now(SEOUL_TZ).strftime('%Y%m%d')}"
            result = self._client.place_market_ioc(
                stock_code, "SELL", remaining, "NXT",
                idempotency_key=idem, paper_mode=(paper or dry_run),
            )
            ioc_req = OrderRequest(
                ticker=stock_code, side="SELL", qty=remaining, price=0, venue="NXT",
                order_type="MARKET_IOC", idempotency_key=idem, note="IOC-final",
            )
            _record_order_to_db(ioc_req, result, "IOC")
            results.append(result)

        return results

    def _execute_trailing_sell(
        self,
        *,
        results: list[OrderResult],
        stock_code: str,
        remaining: int,
        reference_close: int,
        high_price: int,
        paper: bool,
        dry_run: bool,
    ) -> int:
        for minute in range(6, 50):
            self._wait_until(8, minute)
            if remaining <= 0:
                break
            snap = self._client.get_quote_snapshot(stock_code, venue="NXT")
            current_price = self._snapshot_price(snap)
            if current_price <= 0:
                continue
            if current_price > high_price:
                high_price = current_price
                continue

            pullback = high_price > 0 and current_price <= int(
                high_price * (1.0 - SELL_TRAIL_PULLBACK_PCT / 100.0)
            )
            current_change = self._change_pct(current_price, reference_close)
            profit_floor = current_change is not None and current_change <= SELL_TRAIL_PROFIT_FLOOR_PCT
            if pullback or profit_floor:
                price = compute_sell_price(snap, "BID1_TAKER")
                qty = remaining
                remaining -= self._place_sell_and_reserve(
                    results, stock_code, qty, price, "S-trail-stop", paper, dry_run
                )
                break
        return remaining

    def _execute_staged_sell(
        self,
        *,
        results: list[OrderResult],
        stock_code: str,
        remaining: int,
        first_sell_snap: QuoteSnapshot,
        paper: bool,
        dry_run: bool,
    ) -> int:
        half = remaining // 2
        if half > 0:
            price = compute_sell_price(first_sell_snap, "LAST_MINUS_PCT", discount_pct=0.0)
            remaining -= self._place_sell_and_reserve(
                results, stock_code, half, price, "S0-initial50%", paper, dry_run
            )

        self._wait_until(8, 4)
        if remaining > 0:
            snap = self._client.get_quote_snapshot(stock_code, venue="NXT")
            price = compute_sell_price(snap, "LAST_MINUS_PCT", discount_pct=1.0)
            qty = remaining
            remaining -= self._place_sell_and_reserve(
                results, stock_code, qty, price, "S1-minus1pct", paper, dry_run
            )

        self._wait_until(8, 5)
        if remaining > 0:
            snap = self._client.get_quote_snapshot(stock_code, venue="NXT")
            price = compute_sell_price(snap, "BID1_TAKER")
            qty = remaining
            remaining -= self._place_sell_and_reserve(
                results, stock_code, qty, price, "S3-taker", paper, dry_run
            )

        for minute in range(6, 50):
            self._wait_until(8, minute)
            if remaining <= 0:
                break
            snap = self._client.get_quote_snapshot(stock_code, venue="NXT")
            price = compute_sell_price(snap, "BID1_TAKER")
            qty = remaining
            remaining -= self._place_sell_and_reserve(
                results, stock_code, qty, price, f"S-chase-{minute:02d}", paper, dry_run
            )
        return remaining

    def check_emergency_stop(
        self, stock_code: str, reference_close: int, threshold_pct: float = -3.0
    ) -> bool:
        """긴급 손절: 현재가가 KRX 종가 대비 -3% 이상 하락했는지."""
        snap = self._client.get_quote_snapshot(stock_code, venue="NXT")
        cur = snap.last or snap.bid1
        if cur <= 0 or reference_close <= 0:
            return False
        drop_pct = (cur - reference_close) / reference_close * 100.0
        return drop_pct <= threshold_pct

    # ─── 내부 헬퍼 ───────────────────────────────────
    def _place_sell(self, code: str, qty: int, price: int, tag: str, paper: bool, dry_run: bool) -> OrderResult:
        idem = f"SELL_{code}_{tag}_{datetime.now(SEOUL_TZ).strftime('%Y%m%d%H%M%S')}"
        req = OrderRequest(
            ticker=code, side="SELL", qty=qty, price=price, venue="NXT",
            order_type="LIMIT", idempotency_key=idem, note=tag,
        )
        result = self._client.place_limit_order(req, paper_mode=(paper or dry_run))
        _record_order_to_db(req, result, tag)
        return result

    def _wait_until(self, hour: int, minute: int, second: int = 0) -> None:
        """지정 시각(Seoul)까지 대기. 이미 지난 시간이면 즉시 리턴."""
        now = datetime.now(SEOUL_TZ)
        target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        delta = (target - now).total_seconds()
        if delta > 0:
            time.sleep(min(delta, 3600))  # 1시간 이상은 대기 안함 (안전장치)

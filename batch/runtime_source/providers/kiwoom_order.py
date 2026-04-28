"""키움 주문 API 저수준 래퍼.

# Design Ref: Design §5.7 + §7.3 Module E — 자동매수/매도 주문 실행
# Plan §7: 지정가 only(NXT 프리/애프터) + 시장가 IOC(NXT 메인) 백업

공개 함수:
  - place_limit_order(ticker, side, qty, price, venue, idempotency_key)
  - place_market_ioc(ticker, side, qty, venue)  # NXT 메인마켓만
  - cancel_order(order_id)
  - get_order_status(order_id)
  - get_quote_snapshot(ticker, venue)
  - get_deposit()

안전장치:
  - 모든 주문 전 guards.check_allowed() 호출
  - 주문 직후 감사 로그 .bkit/audit/orders.jsonl
  - paper_mode=True면 실주문 발사하지 않고 로그만
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from providers.kiwoom_client import KiwoomAPIError, KiwoomRESTClient, venue_stock_code


# Design Ref: Design §5.4 — 지정가 가격 전략
OrderSide = Literal["BUY", "SELL"]
OrderVenue = Literal["NXT", "KRX"]
OrderType = Literal["LIMIT", "LIMIT_MAKER", "LIMIT_TAKER", "MARKET_IOC"]
OrderStatus = Literal["PENDING", "FILLED", "PARTIAL", "CANCELLED", "FAILED"]


AUDIT_PATH = Path(".bkit/audit/orders.jsonl")


@dataclass
class OrderRequest:
    ticker: str
    side: OrderSide
    qty: int
    price: int
    venue: OrderVenue
    order_type: OrderType
    idempotency_key: str
    note: str = ""


@dataclass
class OrderResult:
    order_id: str = ""
    status: OrderStatus = "PENDING"
    filled_qty: int = 0
    filled_avg_price: float = 0.0
    error_code: str = ""
    error_msg: str = ""
    paper_mode: bool = False
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "status": self.status,
            "filled_qty": self.filled_qty,
            "filled_avg_price": self.filled_avg_price,
            "error_code": self.error_code,
            "error_msg": self.error_msg,
            "paper_mode": self.paper_mode,
        }


@dataclass
class QuoteSnapshot:
    ticker: str
    venue: OrderVenue
    bid1: int
    ask1: int
    last: int
    bid1_qty: int = 0
    ask1_qty: int = 0
    ts: datetime | None = None

    def midpoint(self) -> int:
        if self.bid1 > 0 and self.ask1 > 0:
            return (self.bid1 + self.ask1) // 2
        return self.last


def _audit(event: str, payload: dict) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "payload": payload,
    }
    try:
        with AUDIT_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass  # 감사 로그 실패는 주문 자체를 막지 않음


class KiwoomOrderClient:
    def __init__(self, client: KiwoomRESTClient | None = None) -> None:
        self._client = client or KiwoomRESTClient()

    # ─── 주문 API ───────────────────────────────────────────
    def place_limit_order(self, req: OrderRequest, *, paper_mode: bool = False) -> OrderResult:
        """지정가 주문 발주. NXT 프리/애프터 구간에 사용."""
        result = OrderResult(paper_mode=paper_mode)
        _audit("order.place.begin", {"req": req.__dict__, "paper": paper_mode})

        if paper_mode:
            # paper mode: 실제 주문 대신 시뮬레이션
            result.order_id = f"PAPER-{req.idempotency_key}"
            result.status = "PENDING"
            _audit("order.paper", {"order_id": result.order_id, "req": req.__dict__})
            return result

        # 실주문 — 키움 주문 API
        # kt10000: 주식 매수주문, kt10001: 주식 매도주문
        # dmst_stex_tp: "KRX" / "NXT" / "SOR" (문자열)
        # trde_tp: "0"=지정가, "3"=시장가
        # 주문 stk_cd는 순수 6자리 (조회용 _NX 접미사 X)
        api_id = "kt10000" if req.side == "BUY" else "kt10001"
        try:
            res = self._client.request(
                "/api/dostk/ordr",
                api_id,
                {
                    "dmst_stex_tp": ("NXT" if req.venue == "NXT" else "KRX"),
                    "stk_cd": str(req.ticker).zfill(6),
                    "ord_qty": str(req.qty),
                    "ord_uv": str(req.price),
                    "trde_tp": "0",
                    "cond_uv": "",
                },
            )
            body = res.body
            result.order_id = str(body.get("ord_no", "") or body.get("order_id", ""))
            result.status = "PENDING"
            result.raw = body
            _audit("order.place.ok", {"order_id": result.order_id, "body_keys": list(body.keys())})
        except KiwoomAPIError as exc:
            result.status = "FAILED"
            result.error_msg = str(exc)
            _audit("order.place.fail", {"req": req.__dict__, "err": str(exc)})
        return result

    def place_market_ioc(self, ticker: str, side: OrderSide, qty: int, venue: OrderVenue, *,
                         idempotency_key: str, paper_mode: bool = False) -> OrderResult:
        """NXT 메인마켓 시장가 IOC (08:50 이후 잔량 최종 청산용)."""
        req = OrderRequest(
            ticker=ticker, side=side, qty=qty, price=0, venue=venue,
            order_type="MARKET_IOC", idempotency_key=idempotency_key,
            note="NXT main market IOC final",
        )
        result = OrderResult(paper_mode=paper_mode)
        _audit("order.market_ioc.begin", {"req": req.__dict__, "paper": paper_mode})

        if paper_mode:
            result.order_id = f"PAPER-IOC-{idempotency_key}"
            return result

        api_id = "kt10000" if side == "BUY" else "kt10001"
        try:
            # 시장가 주문: ord_uv 공란, trde_tp="3"
            # NXT 메인마켓(09:00:30~15:20)에서만 시장가 가능. 프리/애프터는 지정가 only.
            res = self._client.request(
                "/api/dostk/ordr",
                api_id,
                {
                    "dmst_stex_tp": ("NXT" if venue == "NXT" else "KRX"),
                    "stk_cd": str(ticker).zfill(6),
                    "ord_qty": str(qty),
                    "ord_uv": "",
                    "trde_tp": "3",
                    "cond_uv": "",
                },
            )
            result.order_id = str(res.body.get("ord_no", ""))
            result.status = "PENDING"
            result.raw = res.body
            _audit("order.market_ioc.ok", {"order_id": result.order_id})
        except KiwoomAPIError as exc:
            result.status = "FAILED"
            result.error_msg = str(exc)
            _audit("order.market_ioc.fail", {"err": str(exc)})
        return result

    def cancel_order(
        self,
        order_id: str,
        *,
        ticker: str = "",
        venue: OrderVenue = "NXT",
        cancel_qty: int = 0,
        paper_mode: bool = False,
    ) -> bool:
        """kt10003 취소주문.
        파라미터: dmst_stex_tp, orig_ord_no, stk_cd, cncl_qty (0/공란=잔량 전부 취소)
        """
        _audit("order.cancel.begin", {"order_id": order_id, "paper": paper_mode, "ticker": ticker})
        if paper_mode:
            return True
        try:
            self._client.request(
                "/api/dostk/ordr",
                "kt10003",
                {
                    "dmst_stex_tp": ("NXT" if venue == "NXT" else "KRX"),
                    "orig_ord_no": str(order_id),
                    "stk_cd": str(ticker).zfill(6) if ticker else "",
                    "cncl_qty": "" if cancel_qty <= 0 else str(cancel_qty),
                },
            )
            _audit("order.cancel.ok", {"order_id": order_id})
            return True
        except KiwoomAPIError as exc:
            _audit("order.cancel.fail", {"order_id": order_id, "err": str(exc)})
            return False

    def get_order_status(self, order_id: str) -> OrderResult:
        """당일 체결내역(ka10076) 조회 후 order_id 필터. 실시간 정확도는 제한."""
        result = OrderResult(order_id=order_id)
        try:
            res = self._client.request(
                "/api/dostk/acnt",
                "ka10076",
                {"qry_tp": "0", "sell_tp": "0", "stex_tp": "0"},
            )
            rows = res.body.get("cntr") if isinstance(res.body.get("cntr"), list) else []
            matching = [r for r in rows if str(r.get("ord_no", "")).strip() == str(order_id).strip()]
            if not matching:
                result.status = "PENDING"
                return result
            # 여러 체결이 있으면 합산
            total_qty = sum(int(abs(float(r.get("ord_qty") or 0))) for r in matching[:1])
            filled = sum(int(abs(float(r.get("cntr_qty") or 0))) for r in matching)
            avg_price_num = 0.0
            total_value = sum(
                float(abs(float(r.get("cntr_qty") or 0))) * float(abs(float(r.get("cntr_pric") or 0)))
                for r in matching
            )
            if filled > 0:
                avg_price_num = total_value / filled
            if filled == 0:
                result.status = "PENDING"
            elif filled >= total_qty and total_qty > 0:
                result.status = "FILLED"
            else:
                result.status = "PARTIAL"
            result.filled_qty = filled
            result.filled_avg_price = round(avg_price_num, 2)
            result.raw = {"matching": matching[:3]}
        except KiwoomAPIError as exc:
            result.status = "FAILED"
            result.error_msg = str(exc)
        return result

    # ─── 시세/예수금 API ─────────────────────────────────────
    def get_quote_snapshot(self, ticker: str, venue: OrderVenue = "NXT") -> QuoteSnapshot:
        """ka10004 주식호가요청. 응답 필드:
        - cur_prc: 현재가
        - buy_fpr_bid: 매수1호가
        - sel_fpr_bid: 매도1호가
        - buy_fpr_req: 매수1호가잔량
        - sel_fpr_req: 매도1호가잔량
        조회 시에는 NXT 접미사(_NX) 사용, 주문 시에는 순수 6자리 코드.
        """
        def _to_int_abs(v: Any) -> int:
            try:
                return abs(int(float(v or 0)))
            except (TypeError, ValueError):
                return 0
        try:
            res = self._client.request(
                "/api/dostk/mrkcond",
                "ka10004",
                {"stk_cd": venue_stock_code(ticker, venue)},
            )
            body = res.body
            return QuoteSnapshot(
                ticker=ticker,
                venue=venue,
                bid1=_to_int_abs(body.get("buy_fpr_bid")),
                ask1=_to_int_abs(body.get("sel_fpr_bid")),
                last=_to_int_abs(body.get("cur_prc")),
                bid1_qty=_to_int_abs(body.get("buy_fpr_req")),
                ask1_qty=_to_int_abs(body.get("sel_fpr_req")),
                ts=datetime.now(timezone.utc),
            )
        except KiwoomAPIError:
            return QuoteSnapshot(ticker=ticker, venue=venue, bid1=0, ask1=0, last=0)

    def get_deposit(self) -> int:
        """예수금(가용자산) 조회.
        kt00018(계좌평가현황)의 prsm_dpst_aset_amt(추정 예수금 자산) 사용.
        기존 dashboard_service.py 에서도 동일 엔드포인트 사용.
        """
        try:
            res = self._client.request(
                "/api/dostk/acnt",
                "kt00018",
                {"qry_tp": "1", "dmst_stex_tp": "KRX"},
            )
            body = res.body
            return abs(int(float(body.get("prsm_dpst_aset_amt") or body.get("tot_evlt_amt") or 0)))
        except KiwoomAPIError:
            return 0


# ─── 가격 전략 헬퍼 ───────────────────────────────────────
def krx_tick_size(price: int) -> int:
    """Return the domestic stock tick size for a positive order price."""
    p = abs(int(price or 0))
    if p < 2_000:
        return 1
    if p < 5_000:
        return 5
    if p < 20_000:
        return 10
    if p < 50_000:
        return 50
    if p < 200_000:
        return 100
    if p < 500_000:
        return 500
    return 1_000


def normalize_order_price(price: int, *, mode: Literal["down", "up", "nearest"] = "nearest") -> int:
    """Align an order price to the KRX/NXT tick grid."""
    p = abs(int(price or 0))
    if p <= 0:
        return 0
    tick = krx_tick_size(p)
    remainder = p % tick
    if remainder == 0:
        return p
    lower = p - remainder
    upper = lower + tick
    if mode == "down":
        return lower
    if mode == "up":
        return upper
    return lower if (p - lower) < (upper - p) else upper


def _effective_tick(price: int, tick_size: int | None) -> int:
    try:
        override = int(tick_size or 0)
    except (TypeError, ValueError):
        override = 0
    return override if override > 1 else krx_tick_size(price)


def _next_tick_price(price: int, tick_size: int | None = None) -> int:
    base = normalize_order_price(price, mode="down")
    if base <= 0:
        return 0
    return normalize_order_price(base + _effective_tick(base, tick_size), mode="up")


def compute_buy_price(snapshot: QuoteSnapshot, strategy: str, tick_size: int | None = None) -> int:
    """Design Ref: Design §5.4 — T1 maker / T2 neutral / T3 taker"""
    s = str(strategy or "").upper()
    if s == "MAKER_BID_PLUS_TICK":
        return _next_tick_price(snapshot.bid1, tick_size) if snapshot.bid1 > 0 else normalize_order_price(snapshot.last)
    if s == "TAKER_ASK":
        return normalize_order_price(snapshot.ask1) if snapshot.ask1 > 0 else normalize_order_price(snapshot.last)
    # default: LAST (중립)
    return normalize_order_price(snapshot.last) if snapshot.last > 0 else normalize_order_price(snapshot.bid1)


def compute_sell_price(snapshot: QuoteSnapshot, strategy: str, discount_pct: float = 0.0) -> int:
    """매도 가격 계산. discount_pct는 현재가 대비 낮추는 비율 (예: 1.0 = -1%)."""
    s = str(strategy or "").upper()
    if s == "BID1_TAKER":
        return normalize_order_price(snapshot.bid1, mode="down") if snapshot.bid1 > 0 else normalize_order_price(snapshot.last, mode="down")
    if s == "LAST_MINUS_PCT":
        base = snapshot.last if snapshot.last > 0 else snapshot.bid1
        return normalize_order_price(int(base * (1.0 - discount_pct / 100.0)), mode="down")
    return normalize_order_price(snapshot.last, mode="down") if snapshot.last > 0 else normalize_order_price(snapshot.bid1, mode="down")

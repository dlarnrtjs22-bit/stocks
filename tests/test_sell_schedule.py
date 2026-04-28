from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


RUNTIME_SOURCE = Path(__file__).resolve().parents[1] / "batch" / "runtime_source"
if str(RUNTIME_SOURCE) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SOURCE))

from executor import guards  # noqa: E402
from executor import trade_executor  # noqa: E402
from executor.trade_executor import TradeExecutor  # noqa: E402
from providers.kiwoom_order import OrderResult, QuoteSnapshot  # noqa: E402


class FakeOrderClient:
    def __init__(self, snapshots: list[QuoteSnapshot] | None = None) -> None:
        self.requests: list[object] = []
        self._snapshots = list(snapshots or [])

    def get_quote_snapshot(self, ticker: str, venue: str = "NXT") -> QuoteSnapshot:
        if self._snapshots:
            return self._snapshots.pop(0)
        return QuoteSnapshot(ticker=ticker, venue="NXT", bid1=99_000, ask1=100_000, last=100_000)

    def place_limit_order(self, req: object, *, paper_mode: bool = False) -> OrderResult:
        self.requests.append(req)
        return OrderResult(order_id=f"ord-{len(self.requests)}", status="PENDING", paper_mode=paper_mode)

    def place_market_ioc(
        self,
        ticker: str,
        side: str,
        qty: int,
        venue: str,
        *,
        idempotency_key: str,
        paper_mode: bool = False,
    ) -> OrderResult:
        self.requests.append(SimpleNamespace(ticker=ticker, side=side, qty=qty, note="IOC-final"))
        return OrderResult(order_id=f"ioc-{len(self.requests)}", status="PENDING", paper_mode=paper_mode)


class SellScheduleTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_check_allowed = guards.check_allowed
        self._original_record_order = trade_executor._record_order_to_db
        guards.check_allowed = lambda *args, **kwargs: SimpleNamespace(allowed=True, paper=False, reason="")
        trade_executor._record_order_to_db = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        guards.check_allowed = self._original_check_allowed
        trade_executor._record_order_to_db = self._original_record_order

    def test_does_not_reorder_same_remaining_quantity_after_sell_order_is_accepted(self) -> None:
        client = FakeOrderClient()
        executor = TradeExecutor(order_client=client)
        executor._wait_until = lambda *args, **kwargs: None  # type: ignore[method-assign]

        executor.execute_sell_schedule(
            position_qty=3,
            stock_code="010120",
            reference_close=100_000,
        )

        self.assertEqual(["S0-initial50%", "S1-minus1pct"], [req.note for req in client.requests])
        self.assertEqual([1, 2], [req.qty for req in client.requests])

    def test_rising_open_waits_and_uses_trailing_exit_instead_of_initial_half_sell(self) -> None:
        snapshots = [
            QuoteSnapshot("010120", "NXT", bid1=99_500, ask1=100_000, last=100_000),
            QuoteSnapshot("010120", "NXT", bid1=102_500, ask1=103_000, last=103_000),
            QuoteSnapshot("010120", "NXT", bid1=104_500, ask1=105_000, last=105_000),
            QuoteSnapshot("010120", "NXT", bid1=103_900, ask1=104_000, last=104_000),
        ]
        client = FakeOrderClient(snapshots)
        executor = TradeExecutor(order_client=client)
        executor._wait_until = lambda *args, **kwargs: None  # type: ignore[method-assign]

        executor.execute_sell_schedule(
            position_qty=3,
            stock_code="010120",
            reference_close=100_000,
        )

        self.assertEqual(["S-trail-stop"], [req.note for req in client.requests])
        self.assertEqual([3], [req.qty for req in client.requests])

    def test_defensive_drop_sells_all_without_waiting_for_staged_orders(self) -> None:
        snapshots = [
            QuoteSnapshot("010120", "NXT", bid1=97_500, ask1=98_000, last=98_000),
        ]
        client = FakeOrderClient(snapshots)
        executor = TradeExecutor(order_client=client)
        executor._wait_until = lambda *args, **kwargs: None  # type: ignore[method-assign]

        executor.execute_sell_schedule(
            position_qty=3,
            stock_code="010120",
            reference_close=100_000,
        )

        self.assertEqual(["S0-defense-drop"], [req.note for req in client.requests])
        self.assertEqual([3], [req.qty for req in client.requests])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path


RUNTIME_SOURCE = Path(__file__).resolve().parents[1] / "batch" / "runtime_source"
if str(RUNTIME_SOURCE) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SOURCE))

from providers.kiwoom_order import (  # noqa: E402
    QuoteSnapshot,
    compute_buy_price,
    compute_sell_price,
    krx_tick_size,
    normalize_order_price,
)


class KiwoomOrderPriceTest(unittest.TestCase):
    def test_maker_bid_plus_tick_uses_krx_tick_size(self) -> None:
        snapshot = QuoteSnapshot(
            ticker="226950",
            venue="NXT",
            bid1=182_900,
            ask1=183_400,
            last=183_400,
        )

        self.assertEqual(100, krx_tick_size(snapshot.bid1))
        self.assertEqual(183_000, compute_buy_price(snapshot, "MAKER_BID_PLUS_TICK"))

    def test_last_and_ask_prices_are_normalized_to_valid_ticks(self) -> None:
        snapshot = QuoteSnapshot(
            ticker="226950",
            venue="NXT",
            bid1=182_900,
            ask1=183_401,
            last=183_451,
        )

        self.assertEqual(183_400, compute_buy_price(snapshot, "TAKER_ASK"))
        self.assertEqual(183_500, compute_buy_price(snapshot, "LAST"))

    def test_sell_last_minus_pct_rounds_down_to_valid_tick(self) -> None:
        snapshot = QuoteSnapshot(
            ticker="226950",
            venue="NXT",
            bid1=182_900,
            ask1=183_400,
            last=183_400,
        )

        self.assertEqual(181_500, compute_sell_price(snapshot, "LAST_MINUS_PCT", discount_pct=1.0))
        self.assertEqual(182_900, normalize_order_price(182_901, mode="down"))


if __name__ == "__main__":
    unittest.main()

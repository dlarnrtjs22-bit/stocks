from __future__ import annotations

import sys
import unittest
from pathlib import Path


RUNTIME_SOURCE = Path(__file__).resolve().parents[1] / "batch" / "runtime_source"
if str(RUNTIME_SOURCE) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SOURCE))

from executor.runner_sell import _position_from_order_row  # noqa: E402


class RunnerSellTest(unittest.TestCase):
    def test_uses_account_position_when_buy_order_is_pending_but_account_holds_shares(self) -> None:
        row = {
            "stock_code": "226950",
            "filled_qty": 0,
            "ordered_qty": 6,
            "quantity": 6,
            "available_qty": 6,
            "filled_avg_price": 0,
            "account_avg_price": 183400,
        }

        self.assertEqual(
            {"stock_code": "226950", "qty": 6, "avg_price": 183400.0},
            _position_from_order_row(row),
        )

    def test_limits_account_fallback_to_ordered_quantity(self) -> None:
        row = {
            "stock_code": "226950",
            "filled_qty": 0,
            "ordered_qty": 6,
            "quantity": 10,
            "available_qty": 10,
            "filled_avg_price": 0,
            "account_avg_price": 183400,
        }

        self.assertEqual(6, _position_from_order_row(row)["qty"])


if __name__ == "__main__":
    unittest.main()

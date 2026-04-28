from __future__ import annotations

import unittest
from types import SimpleNamespace

from backend.app.services.pick_selector import (
    count_buyable_candidates,
    select_official_candidates,
    select_top_2_sector_diverse,
)
from batch.runtime_source.pipelines.daily_candidate_extract import _candidate_rows_from_response


BUY = "\ub9e4\uc218"
SELL = "\ub9e4\ub3c4"


def candidate(
    code: str,
    *,
    score: int,
    rank: int,
    status: str = "WATCH",
    opinion: str = SELL,
    sector: str = "General",
    nxt: bool = True,
) -> dict[str, object]:
    return {
        "stock_code": code,
        "stock_name": f"stock-{code}",
        "signal_rank": rank,
        "score_total": score,
        "grade": "B",
        "base_grade": "B",
        "decision_status": status,
        "ai_opinion": opinion,
        "sector": sector,
        "change_pct": 5.0,
        "trading_value": 100_000_000_000 - rank,
        "nxt_eligible": nxt,
        "news_items": [{"title": "news"}],
    }


class Dumpable:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def model_dump(self) -> dict[str, object]:
        return dict(self.payload)


class CandidateSelectionTest(unittest.TestCase):
    def test_official_candidates_include_buyable_before_filling_watchlist(self) -> None:
        rows = [
            candidate("000001", score=14, rank=1, sector="chips"),
            candidate("000002", score=13, rank=2, sector="bio"),
            candidate("000003", score=12, rank=3, sector="robot"),
            candidate("000004", score=11, rank=4, sector="energy"),
            candidate("000005", score=10, rank=5, sector="ship"),
            candidate("999999", score=8, rank=6, status="BUY", opinion=BUY, sector="software"),
        ]

        selected = select_official_candidates(rows, max_items=5)
        codes = {str(row["stock_code"]) for row in selected}

        self.assertIn("999999", codes)
        self.assertNotIn("000005", codes)
        self.assertEqual(5, len(selected))
        self.assertEqual(1, count_buyable_candidates(selected))

    def test_extract_uses_only_featured_items_as_the_buy_candidate_pool(self) -> None:
        featured = [
            Dumpable(candidate("000001", score=14, rank=1)),
            Dumpable(candidate("000002", score=13, rank=2)),
            Dumpable(candidate("000003", score=12, rank=3)),
            Dumpable(candidate("000004", score=11, rank=4)),
            Dumpable(candidate("000005", score=10, rank=5)),
        ]
        page_items = [
            Dumpable(candidate("999999", score=8, rank=6, status="BUY", opinion=BUY)),
        ]
        response = SimpleNamespace(featured_items=featured, items=page_items)

        rows = _candidate_rows_from_response(response)

        self.assertEqual(["000001", "000002", "000003", "000004", "000005"], [row["stock_code"] for row in rows])
        self.assertNotIn("999999", {row["stock_code"] for row in rows})

    def test_top2_sector_diverse_returns_other_sector_without_unbound_error(self) -> None:
        rows = [
            candidate("000001", score=14, rank=1, status="BUY", opinion=BUY, sector="chips"),
            candidate("000002", score=13, rank=2, status="BUY", opinion=BUY, sector="bio"),
        ]

        selected = select_top_2_sector_diverse(rows)

        self.assertEqual(["000001", "000002"], [row["stock_code"] for row in selected])

    def test_top2_sector_diverse_returns_first_when_only_one_sector_qualifies(self) -> None:
        rows = [
            candidate("000001", score=14, rank=1, status="BUY", opinion=BUY, sector="chips"),
            candidate("000002", score=13, rank=2, status="BUY", opinion=BUY, sector="chips"),
        ]

        selected = select_top_2_sector_diverse(rows)

        self.assertEqual(["000001"], [row["stock_code"] for row in selected])

    def test_top2_sector_diverse_allows_second_when_sector_metadata_is_missing(self) -> None:
        rows = [
            {**candidate("000001", score=14, rank=1, status="BUY", opinion=BUY), "sector": None},
            {**candidate("000002", score=13, rank=2, status="BUY", opinion=BUY), "sector": None},
        ]

        selected = select_top_2_sector_diverse(rows)

        self.assertEqual(["000001", "000002"], [row["stock_code"] for row in selected])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from backend.app.services.closing_bet_service import ClosingBetService


BUY = "\ub9e4\uc218"
SELL = "\ub9e4\ub3c4"


def row(
    code: str,
    *,
    score: int,
    rank: int,
    status: str = "WATCH",
    opinion: str = SELL,
    sector: str = "General",
    grade: str = "B",
    base_grade: str = "B",
    news_items: list[dict[str, object]] | None = None,
    material_news_count: int = 1,
    negative_news_count: int = 0,
    news_tone: str = "mixed",
) -> dict[str, object]:
    return {
        "signal_rank": rank,
        "stock_code": code,
        "stock_name": f"stock-{code}",
        "market": "KOSDAQ",
        "sector": sector,
        "grade": grade,
        "base_grade": base_grade,
        "score_total": score,
        "decision_status": status,
        "ai_opinion": opinion,
        "change_pct": 5.0,
        "trading_value": 100_000_000_000 - rank,
        "entry_price": 10_000,
        "current_price": 10_000,
        "target_price": 11_000,
        "stop_price": 9_000,
        "news_items": [{"title": "news"}] if news_items is None else news_items,
        "material_news_count": material_news_count,
        "negative_news_count": negative_news_count,
        "news_tone": news_tone,
        "ai_evidence": [],
        "ai_breakdown": {},
        "market_context": {},
        "program_context": {},
        "stock_program_context": {},
        "external_market_context": {},
        "market_policy": {},
    }


class FakeRepository:
    def __init__(self, rows: list[dict[str, object]], tracked_rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows
        self.tracked_rows = tracked_rows or []

    def fetch_closing_bundle(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {
            "run_meta": {
                "run_id": "test-run",
                "run_date": date(2026, 4, 24),
                "created_at": datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc),
                "runtime_meta": {},
                "total_candidates": len(self.rows),
                "filtered_count": len(self.rows),
            },
            "aggregate": {
                "total": len(self.rows),
                "signals_count": len(self.rows),
                "grade_s": 0,
                "grade_a": 0,
                "grade_b": len(self.rows),
                "grade_c": 0,
            },
            "featured_rows": self.rows[:5],
            "tracked_rows": self.tracked_rows,
            "selection_rows": self.rows,
            "page_rows": self.rows[5:],
            "list_total": max(len(self.rows) - 5, 0),
            "page": 1,
            "total_pages": 1,
        }


class ClosingBetServiceTest(unittest.TestCase):
    def test_items_are_paginated_after_official_five_are_selected(self) -> None:
        rows = [
            row("000001", score=14, rank=1, sector="chips"),
            row("000002", score=13, rank=2, sector="bio"),
            row("000003", score=12, rank=3, sector="robot"),
            row("000004", score=11, rank=4, sector="energy"),
            row("000005", score=10, rank=5, sector="ship"),
            row("999999", score=8, rank=6, status="BUY", opinion=BUY, sector="software"),
        ]
        service = ClosingBetService(repository=FakeRepository(rows))  # type: ignore[arg-type]

        response = service.get_closing_bet("2026-04-24", "ALL", "", 1, 10)

        featured_codes = [item.ticker for item in response.featured_items]
        page_codes = [item.ticker for item in response.items]

        self.assertIn("999999", featured_codes)
        self.assertNotIn("999999", page_codes)
        self.assertIn("000005", page_codes)
        self.assertEqual(1, response.pagination.total)

    def test_persisted_tracked_picks_are_the_canonical_featured_five(self) -> None:
        rows = [
            row("000001", score=14, rank=1, sector="chips"),
            row("000002", score=13, rank=2, sector="bio"),
            row("000003", score=12, rank=3, sector="robot"),
            row("000004", score=11, rank=4, sector="energy"),
            row("000005", score=10, rank=5, sector="ship"),
            row("999999", score=8, rank=6, status="BUY", opinion=BUY, sector="software"),
        ]
        service = ClosingBetService(repository=FakeRepository(rows, tracked_rows=rows[:5]))  # type: ignore[arg-type]

        response = service.get_closing_bet("2026-04-24", "ALL", "", 1, 10)

        featured_codes = [item.ticker for item in response.featured_items]

        self.assertEqual(["000001", "000002", "000003", "000004", "000005"], featured_codes)
        self.assertNotIn("999999", featured_codes)

    def test_item_preserves_stored_final_and_base_grade(self) -> None:
        rows = [
            row(
                "000001",
                score=13,
                rank=1,
                status="GRADE_BLOCKED",
                grade="C",
                base_grade="B",
            ),
        ]
        service = ClosingBetService(repository=FakeRepository(rows, tracked_rows=rows))  # type: ignore[arg-type]

        response = service.get_closing_bet("2026-04-24", "ALL", "", 1, 10)
        item = response.featured_items[0]

        self.assertEqual("C", item.grade)
        self.assertEqual("B", item.base_grade)
        self.assertEqual("GRADE_BLOCKED", item.decision_status)

    def test_item_exposes_score_quality_separately_from_entry_grade(self) -> None:
        rows = [
            row(
                "000001",
                score=17,
                rank=1,
                grade="B",
                base_grade="B",
            ),
        ]
        service = ClosingBetService(repository=FakeRepository(rows, tracked_rows=rows))  # type: ignore[arg-type]

        response = service.get_closing_bet("2026-04-24", "ALL", "", 1, 10)
        item = response.featured_items[0]

        self.assertEqual("B", item.grade)
        self.assertEqual("A", getattr(item, "quality_grade", None))

    def test_stored_news_blocked_high_score_no_news_is_rejudged_as_buy(self) -> None:
        rows = [
            row(
                "000001",
                score=14,
                rank=1,
                status="NEWS_BLOCKED",
                opinion=SELL,
                grade="S",
                base_grade="S",
                news_items=[],
                material_news_count=0,
            ),
        ]
        service = ClosingBetService(repository=FakeRepository(rows, tracked_rows=rows))  # type: ignore[arg-type]

        response = service.get_closing_bet("2026-04-24", "ALL", "", 1, 10)
        item = response.featured_items[0]

        self.assertEqual(BUY, item.ai_opinion)
        self.assertEqual("BUY", item.decision_status)

    def test_negative_news_hard_blocks_even_when_score_is_buyable(self) -> None:
        rows = [
            row(
                "000001",
                score=14,
                rank=1,
                status="BUY",
                opinion=BUY,
                grade="S",
                base_grade="S",
                news_items=[{"title": "bad news"}],
                material_news_count=1,
                negative_news_count=1,
                news_tone="negative",
            ),
        ]
        service = ClosingBetService(repository=FakeRepository(rows, tracked_rows=rows))  # type: ignore[arg-type]

        response = service.get_closing_bet("2026-04-24", "ALL", "", 1, 10)
        item = response.featured_items[0]

        self.assertEqual(SELL, item.ai_opinion)
        self.assertEqual("NEGATIVE_NEWS_BLOCKED", item.decision_status)


if __name__ == "__main__":
    unittest.main()

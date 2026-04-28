from __future__ import annotations

import asyncio
import unittest

from backend.app.services.dashboard_service import DashboardService


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
    grade: str = "B",
    base_grade: str = "B",
    news_items: list[dict[str, object]] | None = None,
    material_news_count: int = 1,
    negative_news_count: int = 0,
    news_tone: str = "mixed",
) -> dict[str, object]:
    return {
        "run_date": "2026-04-24",
        "signal_rank": rank,
        "stock_code": code,
        "stock_name": f"stock-{code}",
        "market": "KOSDAQ",
        "sector": sector,
        "grade": grade,
        "base_grade": base_grade,
        "score_total": score,
        "trading_value": 100_000_000_000 - rank,
        "change_pct": 5.0,
        "current_price": 10_000,
        "entry_price": 10_000,
        "stop_price": 9_000,
        "target_price": 11_000,
        "foreign_5d": 0,
        "inst_5d": 0,
        "ai_summary": "",
        "ai_opinion": opinion,
        "decision_status": status,
        "ai_evidence": [],
        "news_items": [{"title": "news"}] if news_items is None else news_items,
        "material_news_count": material_news_count,
        "negative_news_count": negative_news_count,
        "news_tone": news_tone,
        "market_context": {},
        "program_context": {},
        "external_market_context": {},
        "market_policy": {},
    }


class FakeDashboardRepository:
    def __init__(self, rows: list[dict[str, object]], tracked_codes: list[str]) -> None:
        self.rows = rows
        self.tracked_codes = tracked_codes
        self.saved_payload: dict[str, object] | None = None

    def fetch_cached_dashboard(self, cache_key: str = "main") -> dict[str, object] | None:
        return None

    def save_cached_dashboard(self, payload: dict[str, object], cache_key: str = "main") -> None:
        self.saved_payload = payload

    def fetch_market_rows(self) -> list[dict[str, object]]:
        return []

    def fetch_program_rows(self) -> list[dict[str, object]]:
        return []

    def fetch_latest_candidates(self, limit: int = 40) -> list[dict[str, object]]:
        return self.rows

    def fetch_latest_tracked_pick_codes(self) -> list[str]:
        return self.tracked_codes

    def fetch_account_snapshot(self) -> dict[str, object] | None:
        return None

    def fetch_account_positions(self, account_no: str | None = None) -> list[dict[str, object]]:
        return []


class DashboardServiceTest(unittest.TestCase):
    def test_dashboard_uses_persisted_tracked_pick_order_when_available(self) -> None:
        rows = [
            candidate("000001", score=14, rank=1, sector="chips"),
            candidate("000002", score=13, rank=2, sector="bio"),
            candidate("000003", score=12, rank=3, sector="robot"),
            candidate("000004", score=11, rank=4, sector="energy"),
            candidate("000005", score=10, rank=5, sector="ship"),
            candidate("999999", score=8, rank=6, status="BUY", opinion=BUY, sector="software"),
        ]
        service = DashboardService(
            repository=FakeDashboardRepository(
                rows,
                tracked_codes=["000001", "000002", "000003", "000004", "000005"],
            )  # type: ignore[arg-type]
        )

        response = asyncio.run(service.get_dashboard(force_refresh=True))

        self.assertEqual(
            ["000001", "000002", "000003", "000004", "000005"],
            [pick.ticker for pick in response.picks],
        )

    def test_dashboard_preserves_stored_final_and_base_grade(self) -> None:
        rows = [
            candidate(
                "000001",
                score=13,
                rank=1,
                status="GRADE_BLOCKED",
                grade="C",
                base_grade="B",
            ),
        ]
        service = DashboardService(
            repository=FakeDashboardRepository(rows, tracked_codes=["000001"])  # type: ignore[arg-type]
        )

        response = asyncio.run(service.get_dashboard(force_refresh=True))
        pick = response.picks[0]

        self.assertEqual("C", pick.grade)
        self.assertEqual("B", pick.base_grade)
        self.assertEqual("GRADE_BLOCKED", pick.decision_status)

    def test_dashboard_rejudges_stored_news_blocked_high_score_as_buy(self) -> None:
        rows = [
            candidate(
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
        service = DashboardService(
            repository=FakeDashboardRepository(rows, tracked_codes=["000001"])  # type: ignore[arg-type]
        )

        response = asyncio.run(service.get_dashboard(force_refresh=True))
        pick = response.picks[0]

        self.assertEqual("BUY", pick.decision_status)

    def test_dashboard_negative_news_blocks_buyable_score(self) -> None:
        rows = [
            candidate(
                "000001",
                score=14,
                rank=1,
                status="BUY",
                opinion=BUY,
                grade="S",
                base_grade="S",
                material_news_count=1,
                negative_news_count=1,
                news_tone="negative",
            ),
        ]
        service = DashboardService(
            repository=FakeDashboardRepository(rows, tracked_codes=["000001"])  # type: ignore[arg-type]
        )

        response = asyncio.run(service.get_dashboard(force_refresh=True))
        pick = response.picks[0]

        self.assertEqual("NEGATIVE_NEWS_BLOCKED", pick.decision_status)


if __name__ == "__main__":
    unittest.main()

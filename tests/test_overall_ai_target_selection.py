from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime
from typing import Any

from batch.runtime_source.engine.config import Grade
from batch.runtime_source.engine.generator import SignalGenerator
from batch.runtime_source.engine.models import ChecklistDetail, ScoreDetail, Signal


class FakeAnalyzer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze_overall_decision(
        self,
        *,
        stock_name: str,
        rule_scores: dict[str, Any],
        metrics: dict[str, Any],
        news_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append(stock_name)
        return {
            "status": "OK",
            "summary": f"ai:{stock_name}",
            "base_grade": metrics.get("base_grade"),
        }

    def build_rule_based_overall(
        self,
        *,
        stock_name: str,
        rule_scores: dict[str, Any],
        metrics: dict[str, Any],
        news_items: list[dict[str, Any]],
        status: str,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "summary": reason,
            "base_grade": metrics.get("base_grade"),
        }


def signal(
    code: str,
    name: str,
    *,
    grade: Grade,
    score_total: int,
    trading_value: int,
) -> Signal:
    return Signal(
        stock_code=code,
        stock_name=name,
        market="KOSPI",
        sector="General",
        signal_date=date(2026, 4, 27),
        signal_time=datetime(2026, 4, 27, 15, 30),
        grade=grade,
        score=ScoreDetail(total=score_total),
        checklist=ChecklistDetail(),
        news_items=[{"title": "news"}],
        ai_overall={"base_grade": grade.value},
        trading_value=trading_value,
    )


class OverallAiTargetSelectionTest(unittest.TestCase):
    def test_overall_ai_targets_match_featured_grade_priority_before_raw_score(self) -> None:
        analyzer = FakeAnalyzer()
        generator = SignalGenerator.__new__(SignalGenerator)
        generator.max_overall_ai_calls = 2
        generator.external_market_context = {}
        generator.llm_analyzer = analyzer
        signals = [
            signal("000660", "SK하이닉스", grade=Grade.A, score_total=19, trading_value=4_447_800_000_000),
            signal("010120", "LS ELECTRIC", grade=Grade.A, score_total=10, trading_value=583_400_000_000),
            signal("267270", "HD현대건설기계", grade=Grade.B, score_total=16, trading_value=160_700_000_000),
        ]

        asyncio.run(generator._apply_overall_ai_topk(signals))

        self.assertEqual(["SK하이닉스", "LS ELECTRIC"], analyzer.calls)
        self.assertEqual("OK", signals[1].ai_overall["status"])
        self.assertEqual("SKIPPED_TOP10", signals[2].ai_overall["status"])


if __name__ == "__main__":
    unittest.main()

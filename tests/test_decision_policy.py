from __future__ import annotations

import unittest
import sys
from pathlib import Path


RUNTIME_SOURCE = Path(__file__).resolve().parents[1] / "batch" / "runtime_source"
if str(RUNTIME_SOURCE) not in sys.path:
    sys.path.insert(0, str(RUNTIME_SOURCE))

from batch.runtime_source.engine.decision_policy import decide_trade_opinion
from batch.runtime_source.engine.models import ScoreDetail


BUY = "\ub9e4\uc218"
SELL = "\ub9e4\ub3c4"


def risk_on_policy(grade: str = "S") -> dict[str, object]:
    return {
        "base_grade": grade,
        "adjusted_grade": grade,
        "market_status": "RISK_ON",
        "risk_score": 70,
        "reasons": [],
    }


class DecisionPolicyTest(unittest.TestCase):
    def test_no_news_does_not_hard_block_high_score_candidate(self) -> None:
        decision = decide_trade_opinion(
            grade="S",
            total_score=14,
            grade_policy=risk_on_policy("S"),
            fresh_news_count=0,
            material_news_count=0,
        )

        self.assertEqual(BUY, decision["opinion"])
        self.assertEqual("BUY", decision["status"])

    def test_negative_news_hard_blocks_candidate(self) -> None:
        decision = decide_trade_opinion(
            grade="S",
            total_score=14,
            grade_policy=risk_on_policy("S"),
            fresh_news_count=1,
            material_news_count=1,
            negative_news_count=1,
            news_tone="negative",
        )

        self.assertEqual(SELL, decision["opinion"])
        self.assertEqual("NEGATIVE_NEWS_BLOCKED", decision["status"])

    def test_score_detail_serializes_material_news_count(self) -> None:
        score = ScoreDetail(material_news_count=1)

        self.assertEqual(1, score.to_dict()["material_news_count"])


if __name__ == "__main__":
    unittest.main()

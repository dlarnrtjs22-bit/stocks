from __future__ import annotations

NEWS_SCORE_MAX = 3
VOLUME_SCORE_MAX = 3
CHART_SCORE_MAX = 2
CANDLE_SCORE_MAX = 1
CONSOLIDATION_SCORE_MAX = 1
SUPPLY_SCORE_MAX = 2
MARKET_SCORE_MAX = 1
PROGRAM_SCORE_MAX = 1
STOCK_PROGRAM_SCORE_MAX = 2
SECTOR_SCORE_MAX = 2
LEADER_SCORE_MAX = 2
INTRADAY_SCORE_MAX = 2
NEWS_ATTENTION_SCORE_MAX = 2
# Design Ref: Design §5 Module B — 수급 연속성 보너스 (외인 + 기관 N일 연속 순매수)
SUPPLY_CONTINUITY_SCORE_MAX = 1

TOTAL_RULE_SCORE_MAX = (
    NEWS_SCORE_MAX
    + VOLUME_SCORE_MAX
    + CHART_SCORE_MAX
    + CANDLE_SCORE_MAX
    + CONSOLIDATION_SCORE_MAX
    + SUPPLY_SCORE_MAX
    + SUPPLY_CONTINUITY_SCORE_MAX
    + MARKET_SCORE_MAX
    + PROGRAM_SCORE_MAX
    + STOCK_PROGRAM_SCORE_MAX
    + SECTOR_SCORE_MAX
    + LEADER_SCORE_MAX
    + INTRADAY_SCORE_MAX
    + NEWS_ATTENTION_SCORE_MAX
)

BUY_SCORE_THRESHOLD = 8

# Score-only quality. This is separate from entry grade, which also depends on
# liquidity and change-rate bands.
QUALITY_GRADE_PRIORITY = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
QUALITY_GRADE_THRESHOLDS = (
    ("S", 18),
    ("A", 14),
    ("B", 10),
    ("C", 8),
    ("D", 0),
)


def score_quality_grade(total_score: object) -> str:
    try:
        score = int(float(total_score))
    except Exception:
        score = 0
    for grade, threshold in QUALITY_GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "D"


def score_quality_priority(total_score: object) -> int:
    return QUALITY_GRADE_PRIORITY.get(score_quality_grade(total_score), 9)

# 연속성 보너스 부여 임계값(수급단타왕 "매일매일 매집")
SUPPLY_CONTINUITY_MIN_DAYS = 3

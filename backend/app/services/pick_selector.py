from __future__ import annotations

from typing import Any


GRADE_PRIORITY = {"S": 0, "A": 1, "B": 2, "C": 3}
BUYABLE_STATUSES = {"BUY"}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _sector_key(row: dict[str, Any], fallback_sector: str) -> str:
    sector_leadership = row.get("sector_leadership") if isinstance(row.get("sector_leadership"), dict) else {}
    sector = str(sector_leadership.get("sector_key", "") or row.get("sector", "") or fallback_sector or "General").strip()
    return sector or "General"


def candidate_priority(row: dict[str, Any], *, fallback_sector: str = "General") -> tuple[Any, ...]:
    base_grade = str(row.get("base_grade", row.get("grade", "C")) or "C").upper()
    final_grade = str(row.get("grade", "C") or "C").upper()
    decision_status = str(row.get("decision_status", "") or "").upper()
    ai_opinion = str(row.get("ai_opinion", "") or "").strip()
    score_total = _safe_int(row.get("score_total"), 0)
    trading_value = _safe_int(row.get("trading_value"), 0)
    change_pct = _safe_float(row.get("change_pct"), 0.0)
    score_sector = _safe_int(row.get("score_sector"), 0)
    score_leader = _safe_int(row.get("score_leader"), 0)
    score_intraday = _safe_int(row.get("score_intraday"), 0)
    score_news_attention = _safe_int(row.get("score_news_attention"), 0)
    fresh_news_count = len(row.get("news_items") if isinstance(row.get("news_items"), list) else [])

    buyable = 1 if (ai_opinion == "매수" and decision_status in BUYABLE_STATUSES) else 0
    watchable = 1 if base_grade in {"S", "A", "B"} else 0
    context_score = (score_sector * 3) + (score_leader * 3) + (score_intraday * 2) + (score_news_attention * 2)
    news_bonus = 2 if fresh_news_count > 0 else 0
    liquidity_bonus = min(4, trading_value // 100_000_000_000)
    return (
        -buyable,
        -watchable,
        GRADE_PRIORITY.get(base_grade, 9),
        GRADE_PRIORITY.get(final_grade, 9),
        -(score_total + context_score + news_bonus + liquidity_bonus),
        -change_pct,
        -trading_value,
        _sector_key(row, fallback_sector),
        str(row.get("stock_code", "") or ""),
    )


def select_top_candidates(
    rows: list[dict[str, Any]],
    *,
    max_items: int = 5,
    fallback_sector: str = "General",
) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: candidate_priority(row, fallback_sector=fallback_sector))
    selected: list[dict[str, Any]] = []
    sector_counts: dict[str, int] = {}

    for row in ordered:
        if len(selected) >= max_items:
            break
        sector = _sector_key(row, fallback_sector)
        current_count = sector_counts.get(sector, 0)
        if current_count >= 1:
            continue
        selected.append(row)
        sector_counts[sector] = current_count + 1

    if len(selected) < max_items:
        selected_codes = {str(row.get("stock_code", "") or "") for row in selected}
        for row in ordered:
            if len(selected) >= max_items:
                break
            code = str(row.get("stock_code", "") or "")
            if code in selected_codes:
                continue
            selected.append(row)
            selected_codes.add(code)

    return selected[:max_items]

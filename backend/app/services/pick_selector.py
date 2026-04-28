from __future__ import annotations

from typing import Any

from batch.runtime_source.engine.scoring_constants import score_quality_priority


GRADE_PRIORITY = {"S": 0, "A": 1, "B": 2, "C": 3}
BUYABLE_STATUSES = {"BUY"}
BUY_OPINIONS = {"\ub9e4\uc218", "BUY", "buy"}


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


def _has_sector_metadata(row: dict[str, Any]) -> bool:
    sector_leadership = row.get("sector_leadership") if isinstance(row.get("sector_leadership"), dict) else {}
    sector = str(sector_leadership.get("sector_key", "") or row.get("sector", "") or "").strip()
    return bool(sector)


def is_buyable_candidate(row: dict[str, Any]) -> bool:
    status = str(row.get("decision_status", "") or "").upper()
    opinion = str(row.get("ai_opinion", "") or "").strip()
    return status in BUYABLE_STATUSES or opinion in BUY_OPINIONS


def candidate_priority(row: dict[str, Any], *, fallback_sector: str = "General") -> tuple[Any, ...]:
    base_grade = str(row.get("base_grade", row.get("grade", "C")) or "C").upper()
    final_grade = str(row.get("grade", "C") or "C").upper()
    score_total = _safe_int(row.get("score_total"), 0)
    trading_value = _safe_int(row.get("trading_value"), 0)
    change_pct = _safe_float(row.get("change_pct"), 0.0)
    score_sector = _safe_int(row.get("score_sector"), 0)
    score_leader = _safe_int(row.get("score_leader"), 0)
    score_intraday = _safe_int(row.get("score_intraday"), 0)
    score_news_attention = _safe_int(row.get("score_news_attention"), 0)
    fresh_news_count = len(row.get("news_items") if isinstance(row.get("news_items"), list) else [])

    buyable = 1 if is_buyable_candidate(row) else 0
    watchable = 1 if base_grade in {"S", "A", "B"} else 0
    context_score = (score_sector * 3) + (score_leader * 3) + (score_intraday * 2) + (score_news_attention * 2)
    news_bonus = 2 if fresh_news_count > 0 else 0
    liquidity_bonus = min(4, trading_value // 100_000_000_000)
    return (
        -buyable,
        -watchable,
        GRADE_PRIORITY.get(base_grade, 9),
        GRADE_PRIORITY.get(final_grade, 9),
        score_quality_priority(score_total),
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


def select_official_candidates(
    rows: list[dict[str, Any]],
    *,
    max_items: int = 5,
    fallback_sector: str = "General",
) -> list[dict[str, Any]]:
    return select_top_candidates(rows, max_items=max_items, fallback_sector=fallback_sector)


def count_buyable_candidates(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if is_buyable_candidate(row))


# Design Ref: Design §6.2 Module C — NXT 가능 + Top 2 (섹터 다양성, 강세 섹터 예외)
# Plan §6.2: 기본 다른 섹터, 예외로 같은 섹터 강세(sector_score=2 + leader=2 둘 다 + 섹터 상승률≥5%)
def _same_sector_strong_exception(
    top: dict[str, Any],
    candidates: list[dict[str, Any]],
    thresholds: dict[str, float],
) -> dict[str, Any] | None:
    """1등 종목과 같은 섹터인 2등 대장주 반환 (조건 만족 시). 없으면 None."""
    top_sector = _sector_key(top, "General")
    top_sector_score = _safe_int(top.get("score_sector"))
    top_leader_score = _safe_int(top.get("score_leader"))
    if top_sector_score < int(thresholds.get("sector_score", 2)):
        return None
    if top_leader_score < int(thresholds.get("leader_score", 2)):
        return None

    same_sector = [r for r in candidates if _sector_key(r, "General") == top_sector and r is not top]
    if not same_sector:
        return None
    # 섹터 상승률 평균 체크
    avg_change = sum(_safe_float(r.get("change_pct"), 0.0) for r in same_sector) / len(same_sector)
    if avg_change < float(thresholds.get("sector_avg_change_pct", 5.0)):
        return None
    # 같은 섹터 내 leader_score=2인 2등 후보 찾기
    for r in same_sector:
        if _safe_int(r.get("score_leader")) >= int(thresholds.get("leader_score", 2)):
            return r
    return None


def select_top_2_sector_diverse(
    rows: list[dict[str, Any]],
    *,
    fallback_sector: str = "General",
    require_nxt_eligible: bool = True,
    require_buy_status: bool = True,
    same_sector_thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Module C: NXT 가능 + 매수 판정 종목만 대상, Top 2 섹터 다양성.

    예외: 섹터 강세면 같은 섹터 2등 대장주 허용.
    """
    thresholds = same_sector_thresholds or {
        "sector_score": 2,
        "leader_score": 2,
        "sector_avg_change_pct": 5.0,
    }

    # 1차 필터: NXT 가능 + 매수 판정
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if require_nxt_eligible and not bool(row.get("nxt_eligible", False)):
            continue
        if require_buy_status:
            if not is_buyable_candidate(row):
                continue
        filtered.append(row)

    if not filtered:
        return []

    ordered = sorted(filtered, key=lambda row: candidate_priority(row, fallback_sector=fallback_sector))
    if len(ordered) < 2:
        return ordered[:1]

    first = ordered[0]
    first_sector = _sector_key(first, fallback_sector)

    # 1) 다른 섹터 2등 우선 탐색
    for row in ordered[1:]:
        if _sector_key(row, fallback_sector) != first_sector:
            # 2등 선정 전에 "강세 섹터 예외 성립 시 같은 섹터 2등이 더 강하면" 오버라이드
            same_sector_alt = _same_sector_strong_exception(first, ordered, thresholds)
            if same_sector_alt is not None:
                # 같은 섹터 2등의 score_total이 다른 섹터 2등보다 더 높으면 override
                if _safe_int(same_sector_alt.get("score_total")) > _safe_int(row.get("score_total")):
                    return [first, same_sector_alt]
            return [first, row]

    # 2) 다른 섹터 후보 없음 → 같은 섹터 강세 예외 적용
    same_sector_alt = _same_sector_strong_exception(first, ordered, thresholds)
    if same_sector_alt is not None:
        return [first, same_sector_alt]

    if not any(_has_sector_metadata(row) for row in ordered):
        return ordered[:2]

    # 3) 후보 부족
    return [first]

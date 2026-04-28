from __future__ import annotations

from typing import Any, Dict, List, Optional

from .scoring_constants import BUY_SCORE_THRESHOLD, TOTAL_RULE_SCORE_MAX


GRADE_ORDER = ("S", "A", "B", "C")


def normalize_grade(grade: Any) -> str:
    value = str(grade or "C").strip().upper()
    return value if value in {"S", "A", "B", "C"} else "C"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _shift_grade(grade: str, steps: int) -> str:
    normalized = normalize_grade(grade)
    idx = GRADE_ORDER.index(normalized)
    return GRADE_ORDER[min(len(GRADE_ORDER) - 1, idx + max(0, int(steps)))]


def _normalize_context(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def apply_market_grade_policy(
    *,
    base_grade: Any,
    market_context: Optional[Dict[str, Any]] = None,
    program_context: Optional[Dict[str, Any]] = None,
    external_market_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_grade = normalize_grade(base_grade)
    local_market = _normalize_context(market_context)
    program = _normalize_context(program_context)
    external = _normalize_context(external_market_context)

    risk_score = 50.0
    reasons: List[str] = []

    market_label = str(local_market.get("market_label") or local_market.get("market") or "시장")
    change_pct = _safe_float(local_market.get("change_pct"), 0.0)
    rise_count = _safe_int(local_market.get("rise_count"), 0)
    fall_count = _safe_int(local_market.get("fall_count"), 0)
    breadth = rise_count - fall_count

    if change_pct <= -1.5:
        risk_score -= 10
        reasons.append(f"{market_label} 지수가 {change_pct:+.2f}%로 약세라 당일 추세 추종 난도가 높습니다.")
    elif change_pct <= -0.7:
        risk_score -= 6
        reasons.append(f"{market_label} 지수가 {change_pct:+.2f}%로 밀려 보수적 접근이 필요합니다.")
    elif change_pct >= 0.8:
        risk_score += 4
        reasons.append(f"{market_label} 지수가 {change_pct:+.2f}%로 우호적인 흐름입니다.")

    if breadth <= -300:
        risk_score -= 6
        reasons.append(f"{market_label} breadth가 약해 하락 종목이 크게 우세합니다.")
    elif breadth <= -120:
        risk_score -= 3
        reasons.append(f"{market_label} breadth가 약세라 종목 확산이 좋지 않습니다.")
    elif breadth >= 200:
        risk_score += 4
        reasons.append(f"{market_label} breadth가 양호해 종목 확산이 받쳐줍니다.")

    total_net = _safe_int(program.get("total_net"), 0)
    non_arbitrage_net = _safe_int(program.get("non_arbitrage_net"), 0)
    if total_net <= -300_000_000_000:
        risk_score -= 6
        reasons.append("프로그램 순매도가 크게 우위라 마감 수급 부담이 큽니다.")
    elif total_net <= -100_000_000_000:
        risk_score -= 3
        reasons.append("프로그램 수급이 순매도 우위라 추격 매수는 주의가 필요합니다.")
    elif total_net >= 100_000_000_000:
        risk_score += 3
        reasons.append("프로그램 수급이 순매수 우위라 마감 수급이 우호적입니다.")

    if non_arbitrage_net <= -200_000_000_000:
        risk_score -= 2
        reasons.append("비차익 매도가 강해 실수급 관점에서도 부담이 있습니다.")
    elif non_arbitrage_net >= 150_000_000_000:
        risk_score += 2
        reasons.append("비차익 매수가 양호해 실수급이 받쳐줍니다.")

    external_status = str(external.get("status", "UNAVAILABLE") or "UNAVAILABLE").strip().upper()
    external_risk_score = round(_safe_float(external.get("risk_score"), 50.0), 2)
    if external_status != "UNAVAILABLE":
        external_delta = (external_risk_score - 50.0) * 0.7
        risk_score += external_delta
        external_evidence = external.get("evidence") if isinstance(external.get("evidence"), list) else []
        for item in external_evidence[:2]:
            text = str(item).strip()
            if text:
                reasons.append(text)

    risk_score = max(0.0, min(100.0, risk_score))
    if risk_score >= 60:
        market_status = "RISK_ON"
        adjustment_steps = 0
        summary = "시장 컨텍스트가 우호적이라 기본 등급을 유지합니다."
    elif risk_score >= 45:
        market_status = "CAUTION"
        adjustment_steps = 1
        summary = "시장 컨텍스트가 혼조라 등급을 한 단계 낮춰 보수적으로 해석합니다."
    else:
        market_status = "RISK_OFF"
        adjustment_steps = 2
        summary = "시장 컨텍스트가 약세라 등급을 두 단계 낮춰 신규 진입을 엄격하게 제한합니다."

    adjusted_grade = _shift_grade(normalized_grade, adjustment_steps)
    reasons.insert(0, f"시장 보정으로 등급이 {normalized_grade} -> {adjusted_grade}로 해석됩니다.")
    reasons.insert(1, summary)

    return {
        "base_grade": normalized_grade,
        "adjusted_grade": adjusted_grade,
        "adjustment_steps": adjustment_steps,
        "market_status": market_status,
        "risk_score": round(risk_score, 2),
        "market_context": local_market,
        "program_context": program,
        "external_market_context": external,
        "reasons": reasons[:5],
    }


def decide_trade_opinion(
    *,
    grade: Any,
    total_score: Any,
    market_context: Optional[Dict[str, Any]] = None,
    program_context: Optional[Dict[str, Any]] = None,
    external_market_context: Optional[Dict[str, Any]] = None,
    grade_policy: Optional[Dict[str, Any]] = None,
    fresh_news_count: Any = None,
    # Design Ref: Design §5 Module B — 실체성 있는 뉴스 카운트 (LLM OK + material_strength>=0.3)
    # 값이 None이면 fallback으로 fresh_news_count를 기준으로 사용 (backward compat).
    # 값이 주어지면 material_news_count == 0 에서 뉴스 가점 없이 점수 기반 판단을 유지한다.
    material_news_count: Any = None,
    negative_news_count: Any = None,
    news_tone: Any = None,
) -> Dict[str, Any]:
    if isinstance(grade_policy, dict) and grade_policy:
        policy = dict(grade_policy)
    else:
        policy = apply_market_grade_policy(
            base_grade=grade,
            market_context=market_context,
            program_context=program_context,
            external_market_context=external_market_context,
        )

    base_grade = normalize_grade(policy.get("base_grade", grade))
    adjusted_grade = normalize_grade(policy.get("adjusted_grade", grade))
    market_status = str(policy.get("market_status", "UNAVAILABLE") or "UNAVAILABLE").strip().upper()
    risk_score = round(_safe_float(policy.get("risk_score"), 50.0), 2)
    total = _safe_int(total_score, 0)
    fresh_news = _safe_int(fresh_news_count, -1)
    # Design Ref: Design §5 Module B — 실체성 있는 뉴스 우선, None이면 fresh_news_count로 fallback
    material_news = _safe_int(material_news_count, -1) if material_news_count is not None else -1
    negative_news = _safe_int(negative_news_count, 0)
    tone = str(news_tone or "").strip().lower()

    reasons: List[str] = [str(item).strip() for item in policy.get("reasons", []) if str(item).strip()]
    opinion = "매도"
    status = "WATCH"

    if adjusted_grade == "C":
        status = "GRADE_BLOCKED"
        reasons.append("시장 보정 후 C등급은 신규 매수 제외 대상입니다.")
    elif total < BUY_SCORE_THRESHOLD:
        status = "SCORE_BLOCKED"
        reasons.append(f"총점 {total}/{TOTAL_RULE_SCORE_MAX}는 전략 진입 기준에 못 미칩니다.")
    else:
        opinion = "매수"
        status = "BUY"
        reasons.append(f"시장 보정 후 {adjusted_grade}등급과 총점 {total}/{TOTAL_RULE_SCORE_MAX} 기준에서는 진입 가능 구간입니다.")

    if negative_news > 0 or tone == "negative":
        opinion = "매도"
        status = "NEGATIVE_NEWS_BLOCKED"
        reasons.append("뚜렷한 악재성 뉴스가 확인되어 신규 진입을 차단합니다.")
    elif material_news == 0:
        reasons.append("실체 있는 재료 뉴스는 약하므로 뉴스 가점 없이 점수 기반 판단만 적용합니다.")
    elif material_news < 0 and fresh_news == 0:
        reasons.append("유효 구간의 직접 뉴스가 없어 뉴스 가점 없이 점수 기반 판단만 적용합니다.")

    if market_status == "RISK_OFF":
        if opinion == "매수":
            opinion = "매도"
            status = "MARKET_BLOCKED"
        reasons.append("시장 컨텍스트가 리스크오프로 판정되어 신규 진입을 보류합니다.")
    elif market_status == "CAUTION":
        if opinion == "매수" and adjusted_grade == "B":
            opinion = "매도"
            status = "MARKET_CAUTION_BLOCK"
            reasons.append("주의장에서는 시장 보정 후 B등급 신규 진입을 보류합니다.")
        elif opinion == "매수":
            reasons.append("주의장이라도 상위 등급 중심의 선별 접근이 필요합니다.")
    elif market_status == "RISK_ON" and opinion == "매수":
        reasons.append("시장 컨텍스트가 우호적이라 매수 판단을 유지합니다.")

    return {
        "opinion": opinion,
        "status": status,
        "grade": adjusted_grade,
        "base_grade": base_grade,
        "adjusted_grade": adjusted_grade,
        "total_score": total,
        "fresh_news_count": fresh_news,
        "material_news_count": material_news,
        "negative_news_count": negative_news,
        "news_tone": tone,
        "market_status": market_status,
        "risk_score": risk_score,
        "grade_policy": policy,
        "reasons": reasons[:5],
    }

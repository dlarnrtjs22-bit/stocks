from __future__ import annotations

from typing import Any


MARKET_STATUS_LABELS = {
    "RISK_ON": "시장 우호",
    "CAUTION": "시장 주의",
    "RISK_OFF": "시장 약세",
    "UNAVAILABLE": "시장 정보 부족",
    "OPEN": "장중",
    "CLOSE": "장마감",
    "CLOSED": "장마감",
}

DECISION_STATUS_LABELS = {
    "BUY": "매수 가능",
    "WATCH": "관찰",
    "GRADE_BLOCKED": "등급 미달",
    "SCORE_BLOCKED": "점수 부족",
    "MARKET_BLOCKED": "시황 때문에 보류",
    "MARKET_CAUTION_BLOCK": "주의장이라 보류",
    "NEWS_BLOCKED": "뉴스 근거 부족",
    "NO_RESULT": "분석 없음",
    "DISABLED": "비활성화",
    "OK": "정상",
}

ANALYSIS_STATUS_LABELS = {
    "OK": "정상",
    "NO_RESULT": "분석 없음",
    "NO_NEWS": "관련 뉴스 없음",
    "FALLBACK": "규칙 기반 분석",
    "DISABLED": "비활성화",
    "SKIPPED_TOP10": "상위 후보 외",
    "JSON_ERROR": "응답 해석 실패",
    "ERROR": "분석 실패",
}

MINUTE_PATTERN_LABELS = {
    "rebreakout": "재돌파",
    "range": "박스권",
    "trend": "상승 추세",
    "pullback": "눌림목",
    "failed_breakout": "돌파 실패",
    "breakdown": "이탈",
    "insufficient": "데이터 부족",
    "": "패턴 없음",
}

PRESSURE_STATUS_LABELS = {
    "STRONG": "강함",
    "SUPPORTIVE": "우호적",
    "MIXED": "혼조",
    "WEAK": "약함",
    "NEUTRAL": "중립",
}


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().upper()


def market_status_label(value: Any) -> str:
    code = _normalize_code(value)
    return MARKET_STATUS_LABELS.get(code, str(value or "-") or "-")


def decision_status_label(value: Any) -> str:
    code = _normalize_code(value)
    return DECISION_STATUS_LABELS.get(code, str(value or "-") or "-")


def analysis_status_label(value: Any) -> str:
    code = _normalize_code(value)
    return ANALYSIS_STATUS_LABELS.get(code, str(value or "-") or "-")


def minute_pattern_label(value: Any) -> str:
    text = str(value or "").strip()
    return MINUTE_PATTERN_LABELS.get(text, text or "패턴 없음")


def pressure_status_label(value: Any) -> str:
    code = _normalize_code(value)
    return PRESSURE_STATUS_LABELS.get(code, str(value or "-") or "-")


def humanize_text(text: Any) -> str:
    out = str(text or "")
    replacements = {
        "RISK_OFF": "시장 약세",
        "RISK_ON": "시장 우호",
        "CAUTION": "시장 주의",
        "WATCH": "관찰",
        "BUY": "매수 가능",
        "GRADE_BLOCKED": "등급 미달",
        "SCORE_BLOCKED": "점수 부족",
        "MARKET_BLOCKED": "시황 때문에 보류",
        "MARKET_CAUTION_BLOCK": "주의장이라 보류",
        "NEWS_BLOCKED": "뉴스 근거 부족",
        "NO_RESULT": "분석 없음",
        "NO_NEWS": "관련 뉴스 없음",
        "FALLBACK": "규칙 기반 분석",
        "DISABLED": "비활성화",
        "SKIPPED_TOP10": "상위 후보 외",
        "STRONG": "강함",
        "SUPPORTIVE": "우호적",
        "MIXED": "혼조",
        "WEAK": "약함",
        "NEUTRAL": "중립",
        "rebreakout": "재돌파",
        "range": "박스권",
        "top_k": "상위 후보 수",
        "RAW ": "원등급 ",
    }
    for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        out = out.replace(old, new)
    return out

from __future__ import annotations

# 이 파일은 화면 응답 조립 시 공통으로 쓰는 보조 함수를 모아 둔다.
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from batch.runtime_source.engine.config import Grade, SignalConfig


_SIGNAL_CONFIG = SignalConfig.default()


# 이 함수는 숫자를 안전하게 float 로 바꾼다.
def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


# 이 함수는 숫자를 안전하게 int 로 바꾼다.
def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


# 이 함수는 날짜 시간을 ISO 문자열에서 datetime 으로 바꾼다.
def safe_dt(value: Any) -> datetime | None:
    try:
        if not value:
            return None
        ts = pd.to_datetime(value, errors='coerce')
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None


# 이 함수는 현재 시점 기준 상대 시간을 사람이 보기 쉬운 문자열로 만든다.
def time_ago(value: Any) -> str:
    dt = safe_dt(value)
    if dt is None:
        return '-'
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    seconds = int((now - dt.astimezone(timezone.utc)).total_seconds())
    if seconds < 60:
        return '방금 전'
    if seconds < 3600:
        return f'{seconds // 60}분 전'
    if seconds < 86400:
        return f'{seconds // 3600}시간 전'
    return f'{seconds // 86400}일 전'


# 이 함수는 날짜 인자를 latest 형식으로 정규화한다.
def normalize_date_arg(date_arg: str | None) -> str:
    if not date_arg or str(date_arg).strip().lower() == 'latest':
        return 'latest'
    return str(date_arg).strip()


def infer_signal_grade(score_total: Any, trading_value: Any, change_pct: Any) -> str:
    score = safe_int(score_total, 0)
    trading = safe_int(trading_value, 0)
    change = safe_float(change_pct, 0.0)
    for grade in (Grade.S, Grade.A, Grade.B):
        cfg = _SIGNAL_CONFIG.grade_configs[grade]
        if trading >= cfg.min_trading_value and cfg.min_change_pct <= change <= cfg.max_change_pct and score >= cfg.min_score:
            return grade.value
    return Grade.C.value


def normalize_signal_grade(value: Any) -> str:
    grade = str(value or '').strip().upper()
    return grade if grade in {'S', 'A', 'B', 'C'} else ''


def resolve_signal_grades(row: dict[str, Any]) -> tuple[str, str]:
    final_grade = normalize_signal_grade(row.get('grade'))
    if not final_grade:
        final_grade = infer_signal_grade(row.get('score_total'), row.get('trading_value'), row.get('change_pct'))
    base_grade = normalize_signal_grade(row.get('base_grade')) or final_grade
    return final_grade, base_grade


# 이 함수는 종목명에서 화면 태그에 사용할 간단한 테마를 추론한다.
def infer_themes(name: str) -> list[str]:
    target = str(name or '').lower()
    themes: list[str] = []
    if any(keyword in target for keyword in ['반도체', 'semicon', 'hynix', '한미반도체']):
        themes.append('반도체')
    if any(keyword in target for keyword in ['바이오', 'bio', 'pharm']):
        themes.append('바이오')
    if any(keyword in target for keyword in ['금융', 'bank', '증권', '보험']):
        themes.append('금융')
    if any(keyword in target for keyword in ['에너지', 'power', 'chemical']):
        themes.append('에너지')
    if any(keyword in target for keyword in ['ai', '로봇', '소프트', '플랫폼']):
        themes.append('AI/플랫폼')
    if not themes:
        themes.append('General')
    return themes[:3]


from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable, List

import pandas as pd


DEFAULT_NEWS_CUTOFF_HOUR = 15
DEFAULT_NEWS_CUTOFF_MINUTE = 30


def build_news_window(
    target_date: date,
    *,
    cutoff_hour: int = DEFAULT_NEWS_CUTOFF_HOUR,
    cutoff_minute: int = DEFAULT_NEWS_CUTOFF_MINUTE,
) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date - timedelta(days=1), time(cutoff_hour, cutoff_minute))
    end = datetime.combine(target_date, time(23, 59, 59, 999999))
    return start, end


def normalize_published_at_series(values: Iterable[object]) -> pd.Series:
    parsed = pd.to_datetime(pd.Series(list(values)), errors="coerce")
    try:
        if getattr(parsed.dt, "tz", None) is not None:
            parsed = parsed.dt.tz_localize(None)
    except Exception:
        pass
    return parsed


def filter_news_frame_by_window(
    df: pd.DataFrame,
    *,
    target_date: date,
    published_at_col: str = "published_at",
    cutoff_hour: int = DEFAULT_NEWS_CUTOFF_HOUR,
    cutoff_minute: int = DEFAULT_NEWS_CUTOFF_MINUTE,
) -> pd.DataFrame:
    if df.empty or published_at_col not in df.columns:
        return df.copy()

    out = df.copy()
    out["published_at_dt"] = normalize_published_at_series(out[published_at_col].tolist())
    start, end = build_news_window(
        target_date,
        cutoff_hour=cutoff_hour,
        cutoff_minute=cutoff_minute,
    )
    mask = (out["published_at_dt"] >= start) & (out["published_at_dt"] <= end)
    return out.loc[mask].reset_index(drop=True)


def extract_news_dates(df: pd.DataFrame, *, published_at_col: str = "published_at") -> List[date]:
    if df.empty or published_at_col not in df.columns:
        return []
    parsed = normalize_published_at_series(df[published_at_col].tolist())
    unique_dates = sorted({value.date() for value in parsed.dropna().tolist()})
    return list(unique_dates)


def describe_news_window(
    target_date: date,
    *,
    cutoff_hour: int = DEFAULT_NEWS_CUTOFF_HOUR,
    cutoff_minute: int = DEFAULT_NEWS_CUTOFF_MINUTE,
) -> str:
    start, end = build_news_window(
        target_date,
        cutoff_hour=cutoff_hour,
        cutoff_minute=cutoff_minute,
    )
    return f"{start.strftime('%Y-%m-%d %H:%M')} 이후 ~ {end.strftime('%Y-%m-%d %H:%M')}"

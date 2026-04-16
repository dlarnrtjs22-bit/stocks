from __future__ import annotations

# 이 파일은 누적 성과 화면 응답 스키마를 정의한다.
from pydantic import BaseModel, Field

from backend.app.schemas.closing_bet import BasisPayload, PaginationPayload


# 이 모델은 누적 성과 상단 요약 값을 담는다.
class PerformanceSummary(BaseModel):
    total_signals: int = 0
    win_rate: float = 0.0
    wins: int = 0
    losses: int = 0
    open: int = 0
    avg_roi: float = 0.0
    total_roi: float = 0.0
    profit_factor: float = 0.0
    avg_days: float = 0.0


class PerformanceComparison(BaseModel):
    better_slot: str = '-'
    win_rate_08: float = 0.0
    win_rate_09: float = 0.0
    edge_pct: float = 0.0


class PerformanceRefreshResponse(BaseModel):
    status: str = 'ok'
    tracked_count: int = 0
    refreshed_08: int = 0
    refreshed_09: int = 0
    skipped_08: int = 0
    skipped_09: int = 0
    message: str = ''


# 이 모델은 등급별 성과 요약 한 줄을 담는다.
class GradeSummaryItem(BaseModel):
    grade: str
    count: int = 0
    win_rate: float = 0.0
    avg_roi: float = 0.0
    wl: str = '0/0'
    win_rate_08: float = 0.0
    avg_roi_08: float = 0.0
    wl_08: str = '0/0'
    win_rate_09: float = 0.0
    avg_roi_09: float = 0.0
    wl_09: str = '0/0'


# 이 모델은 누적 성과 테이블 한 줄을 담는다.
class PerformanceTradeItem(BaseModel):
    key: int
    date: str
    buy_date: str | None = None
    grade: str
    name: str
    ticker: str
    entry: float
    outcome: str
    roi: float
    max_high: float
    price_trail: str
    days: int
    score: int
    themes: list[str] = Field(default_factory=list)
    eval_date: str | None = None
    eval_08_price: float | None = None
    eval_08_time: str | None = None
    eval_08_venue: str | None = None
    outcome_08: str = 'OPEN'
    roi_08: float | None = None
    eval_09_price: float | None = None
    eval_09_time: str | None = None
    eval_09_venue: str | None = None
    outcome_09: str = 'OPEN'
    roi_09: float | None = None


# 이 모델은 누적 성과 전체 응답이다.
class PerformanceResponse(BaseModel):
    date: str
    is_today: bool
    summary: PerformanceSummary = Field(default_factory=PerformanceSummary)
    summary_08: PerformanceSummary = Field(default_factory=PerformanceSummary)
    summary_09: PerformanceSummary = Field(default_factory=PerformanceSummary)
    comparison: PerformanceComparison = Field(default_factory=PerformanceComparison)
    grade_summary: list[GradeSummaryItem] = Field(default_factory=list)
    distribution: dict[str, int] = Field(default_factory=dict)
    trades: list[PerformanceTradeItem] = Field(default_factory=list)
    pagination: PaginationPayload
    basis: BasisPayload


from __future__ import annotations

# 이 파일은 종가배팅 화면 응답 스키마를 정의한다.
from typing import Any

from pydantic import BaseModel, Field


# 이 모델은 기준 정보 패널 한 줄에 필요한 데이터를 담는다.
class BasisSourceItem(BaseModel):
    label: str
    status: str
    updated_at: str | None = None
    updated_ago: str = '-'
    max_data_time: str | None = None
    records: int = 0


# 이 모델은 현재 화면이 어떤 run 기준인지 설명한다.
class BasisPayload(BaseModel):
    request_date: str
    selected_date: str
    run_updated_at: str | None = None
    run_updated_ago: str = '-'
    reference_data_time: str | None = None
    reference_data_ago: str = '-'
    stale_against_inputs: bool = False
    stale_reason: str = ''
    llm_provider: str = ''
    llm_model: str = ''
    llm_calls_used: int = 0
    overall_ai_top_k: int = 0
    sources: list[BasisSourceItem] = Field(default_factory=list)


# 이 모델은 종가배팅 카드 1개를 표현한다.
class ClosingBetItem(BaseModel):
    rank: int
    global_rank: int
    ticker: str
    name: str
    market: str
    grade: str
    base_grade: str = 'C'
    score_total: int
    score_max: int
    scores: dict[str, int] = Field(default_factory=dict)
    change_pct: float = 0.0
    trading_value: int = 0
    entry_price: float = 0.0
    current_price: float = 0.0
    target_price: float = 0.0
    stop_price: float = 0.0
    ai_analysis: str = ''
    analysis_status: str = 'NO_RESULT'
    analysis_status_label: str = ''
    ai_opinion: str = '매도'
    decision_status: str = 'WATCH'
    decision_label: str = ''
    ai_evidence: list[str] = Field(default_factory=list)
    ai_breakdown: dict[str, Any] = Field(default_factory=dict)
    references: list[dict[str, Any]] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    foreign_1d: int = 0
    inst_1d: int = 0
    foreign_5d: int = 0
    inst_5d: int = 0
    market_context: dict[str, Any] = Field(default_factory=dict)
    program_context: dict[str, Any] = Field(default_factory=dict)
    external_market_context: dict[str, Any] = Field(default_factory=dict)
    market_policy: dict[str, Any] = Field(default_factory=dict)
    minute_pattern_label: str = ''
    market_status_label: str = ''
    external_market_status_label: str = ''
    chart_url: str = ''


# 이 모델은 페이지네이션 정보를 표현한다.
class PaginationPayload(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


# 이 모델은 종가배팅 화면 전체 응답이다.
class ClosingBetResponse(BaseModel):
    date: str
    is_today: bool
    status: str
    candidates_count: int
    signals_count: int
    buyable_signals_count: int = 0
    featured_count: int = 0
    grade_counts: dict[str, int] = Field(default_factory=dict)
    featured_items: list[ClosingBetItem] = Field(default_factory=list)
    items: list[ClosingBetItem] = Field(default_factory=list)
    pagination: PaginationPayload
    filters: dict[str, str] = Field(default_factory=dict)
    basis: BasisPayload


# 이 모델은 조회 가능 날짜 목록 응답이다.
class DateListResponse(BaseModel):
    dates: list[str] = Field(default_factory=list)
    latest: str | None = None


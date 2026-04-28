from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DashboardMarketItem(BaseModel):
    market: str
    market_label: str
    market_status: str
    market_status_label: str = ''
    index_value: float
    change_pct: float
    rise_count: int
    steady_count: int
    fall_count: int
    upper_count: int
    lower_count: int
    total_net: int = 0
    non_arbitrage_net: int = 0
    snapshot_time: str | None = None


class DashboardAccountPayload(BaseModel):
    available: bool = False
    account_no: str | None = None
    snapshot_time: str | None = None
    venue: str | None = None
    total_purchase_amt: int = 0
    total_eval_amt: int = 0
    total_eval_profit: int = 0
    total_profit_rate: float = 0.0
    estimated_assets: int = 0
    holdings_count: int = 0
    realized_profit: int = 0
    unfilled_count: int = 0
    total_unfilled_qty: int = 0
    avg_fill_latency_ms: float = 0.0
    est_slippage_bps: float = 0.0
    note: str = ''
    positions: list['DashboardAccountPosition'] = Field(default_factory=list)


class DashboardAccountPosition(BaseModel):
    ticker: str
    stock_name: str
    quantity: int = 0
    available_qty: int = 0
    avg_price: float = 0.0
    current_price: float = 0.0
    eval_amount: int = 0
    profit_amount: int = 0
    profit_rate: float = 0.0


class DashboardPickPayload(BaseModel):
    ticker: str
    name: str
    market: str
    sector: str
    grade: str
    base_grade: str = 'C'
    quality_grade: str = 'D'
    quality_label: str = ''
    decision_status: str = 'WATCH'
    decision_label: str = ''
    score_total: int
    trading_value: int
    change_pct: float
    current_price: float
    entry_price: float
    target_price: float
    stop_price: float
    foreign_1d: int
    inst_1d: int
    foreign_5d: int
    inst_5d: int
    venue: str | None = None
    ai_summary: str = ''
    ai_evidence: list[str] = Field(default_factory=list)
    report_title: str = ''
    report_body: str = ''
    key_points: list[str] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    intraday: dict[str, Any] = Field(default_factory=dict)
    minute_pattern_label: str = ''


class DashboardResponse(BaseModel):
    date: str
    market_summary: str
    markets: list[DashboardMarketItem] = Field(default_factory=list)
    picks: list[DashboardPickPayload] = Field(default_factory=list)
    account: DashboardAccountPayload = Field(default_factory=DashboardAccountPayload)

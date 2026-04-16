from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.dashboard import DashboardAccountPayload


class TradeHistoryDailyItem(BaseModel):
    date: str
    buy_amount: int = 0
    sell_amount: int = 0
    realized_profit: int = 0
    commission: int = 0
    tax: int = 0


class TradeHistoryExecutionItem(BaseModel):
    key: str
    order_no: str
    original_order_no: str | None = None
    ticker: str
    stock_name: str
    side: str = 'ALL'
    order_type: str = ''
    order_status: str = ''
    trade_type: str = ''
    venue: str = ''
    order_qty: int = 0
    filled_qty: int = 0
    unfilled_qty: int = 0
    order_price: float = 0.0
    filled_price: float = 0.0
    order_time: str | None = None
    filled_time: str | None = None
    fee: int = 0
    tax: int = 0
    stop_price: float = 0.0
    sor_yn: str = ''
    fill_latency_ms: float = 0.0
    slippage_bps: float = 0.0


class TradeHistoryResponse(BaseModel):
    date_from: str
    date_to: str
    account: DashboardAccountPayload = Field(default_factory=DashboardAccountPayload)
    daily_summary: list[TradeHistoryDailyItem] = Field(default_factory=list)
    executions: list[TradeHistoryExecutionItem] = Field(default_factory=list)
    filters: dict[str, str] = Field(default_factory=dict)
    refreshed_at: str | None = None

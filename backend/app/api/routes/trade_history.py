from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.schemas.trade_history import TradeHistoryResponse
from backend.app.services.trade_history_service import TradeHistoryService

router = APIRouter(prefix='/api/trade-history', tags=['trade-history'])
service = TradeHistoryService()


@router.get('', response_model=TradeHistoryResponse)
def get_trade_history(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    side: str = Query('ALL'),
    status: str = Query('ALL'),
    q: str = Query(''),
) -> TradeHistoryResponse:
    return service.get_trade_history(
        date_from_arg=date_from,
        date_to_arg=date_to,
        side_filter=side,
        status_filter=status,
        query=q,
    )

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.schemas.dashboard import DashboardResponse
from backend.app.services.dashboard_service import DashboardService

router = APIRouter(prefix='/api/dashboard', tags=['dashboard'])
service = DashboardService()


@router.get('', response_model=DashboardResponse)
async def get_dashboard(refresh_account: bool = Query(False)) -> DashboardResponse:
    return await service.get_dashboard(refresh_account=refresh_account)

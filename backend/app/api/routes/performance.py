from __future__ import annotations

# 이 파일은 누적 성과 화면 API 라우트를 정의한다.
from fastapi import APIRouter, Query

from backend.app.schemas.performance import PerformanceRefreshResponse, PerformanceResponse
from backend.app.services.performance_service import PerformanceService

router = APIRouter(prefix='/api/performance', tags=['performance'])
service = PerformanceService()


# 이 엔드포인트는 누적 성과 화면 전체 데이터를 반환한다.
@router.get('', response_model=PerformanceResponse)
def get_performance(
    date: str = Query('latest'),
    grade: str = Query('ALL'),
    outcome: str = Query('ALL'),
    q: str = Query(''),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=200),
) -> PerformanceResponse:
    return service.get_performance(date, grade.upper(), outcome.upper(), q, page, page_size)


@router.post('/quick-refresh', response_model=PerformanceRefreshResponse)
def quick_refresh_performance(
    date: str = Query('latest'),
) -> PerformanceRefreshResponse:
    return service.quick_refresh(date)


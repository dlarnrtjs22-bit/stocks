from __future__ import annotations

# 이 파일은 종가배팅 화면 API 라우트를 정의한다.
from fastapi import APIRouter, Query

from backend.app.schemas.closing_bet import ClosingBetResponse, DateListResponse
from backend.app.services.closing_bet_service import ClosingBetService

router = APIRouter(prefix='/api/closing-bet', tags=['closing-bet'])
service = ClosingBetService()


# 이 엔드포인트는 날짜 드롭다운에 쓸 run 날짜 목록을 반환한다.
@router.get('/dates', response_model=DateListResponse)
def list_closing_bet_dates() -> dict:
    return service.list_dates()


# 이 엔드포인트는 종가배팅 화면 전체 데이터를 반환한다.
@router.get('', response_model=ClosingBetResponse)
def get_closing_bet(
    date: str = Query('latest'),
    grade: str = Query('ALL'),
    q: str = Query(''),
    page: int = Query(1, ge=1),
    page_size: int = Query(8, ge=1, le=100),
) -> ClosingBetResponse:
    return service.get_closing_bet(date, grade.upper(), q, page, page_size)


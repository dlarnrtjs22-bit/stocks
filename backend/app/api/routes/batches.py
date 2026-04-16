from __future__ import annotations

# 이 파일은 Data Status 와 배치 실행 관련 API 라우트를 정의한다.
from fastapi import APIRouter, Body, HTTPException, Query

from backend.app.schemas.batch import BatchListResponse, BatchLogResponse, BatchRunRequest, PreviewResponse
from backend.app.services.batch_service import BatchService
from backend.app.workers.batch_runner import runner

router = APIRouter(prefix='/api/batches', tags=['batches'])
service = BatchService()


# 이 엔드포인트는 Data Status 화면 전체 데이터를 반환한다.
@router.get('', response_model=BatchListResponse)
def get_batches() -> BatchListResponse:
    return service.get_batch_list()


# 이 엔드포인트는 단일 배치를 시작한다.
@router.post('/{task_id}/run')
def run_batch(task_id: str, payload: BatchRunRequest | None = Body(default=None)) -> dict[str, str]:
    if task_id not in runner.tasks():
        raise HTTPException(status_code=404, detail='unknown task id')
    source = payload.source if payload is not None else 'naver'
    if not service.start_task(task_id, source):
        raise HTTPException(status_code=409, detail='task already running')
    return {'status': 'started', 'task_id': task_id}


# 이 엔드포인트는 모든 배치를 순차 실행한다.
@router.post('/run-all')
def run_all_batches(payload: BatchRunRequest | None = Body(default=None)) -> dict[str, str]:
    source = payload.source if payload is not None else 'naver'
    if not service.start_run_all(source):
        raise HTTPException(status_code=409, detail='run-all already running')
    return {'status': 'started'}


# 이 엔드포인트는 Preview 표 데이터를 반환한다.
@router.get('/{task_id}/preview', response_model=PreviewResponse)
def get_batch_preview(task_id: str, limit: int = Query(20, ge=1, le=100)) -> PreviewResponse:
    if task_id not in runner.tasks():
        raise HTTPException(status_code=404, detail='unknown task id')
    return service.get_preview(task_id, limit)


# 이 엔드포인트는 Logs 모달에서 볼 로그를 반환한다.
@router.get('/{task_id}/logs', response_model=BatchLogResponse)
def get_batch_logs(task_id: str) -> BatchLogResponse:
    if task_id not in runner.tasks():
        raise HTTPException(status_code=404, detail='unknown task id')
    return service.get_logs(task_id)


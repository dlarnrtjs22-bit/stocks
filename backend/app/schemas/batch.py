from __future__ import annotations

# 이 파일은 Data Status 화면 응답에 사용하는 스키마를 정의한다.
from typing import Any

from pydantic import BaseModel, Field


# 이 모델은 개별 배치 카드 한 장의 상태를 표현한다.
class BatchTaskItem(BaseModel):
    id: str
    title: str
    group: str
    output_target: str
    status: str
    running: bool
    updated_at: str | None = None
    updated_ago: str = '-'
    records: int = 0
    run_date: str | None = None
    reference_data_time: str | None = None
    source: str = 'db'
    supported_sources: list[str] = Field(default_factory=list)
    effective_source: str = 'naver'
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None


# 이 모델은 Run All 전체 상태를 표현한다.
class RunAllState(BaseModel):
    running: bool = False
    status: str = 'IDLE'
    started_at: str | None = None
    finished_at: str | None = None
    current_task: str | None = None
    completed_tasks: list[str] = Field(default_factory=list)
    error_task: str | None = None
    error_message: str | None = None


# 이 모델은 배치 상태 화면 전체 응답을 표현한다.
class BatchListResponse(BaseModel):
    tasks: list[BatchTaskItem] = Field(default_factory=list)
    run_all: RunAllState = Field(default_factory=RunAllState)


# 이 모델은 Preview 표 형태 응답을 표현한다.
class PreviewResponse(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


# 이 모델은 로그 조회 응답을 표현한다.
class BatchLogResponse(BaseModel):
    task_id: str
    status: str
    running: bool
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    stdout_tail: str = ''
    stderr_tail: str = ''


class BatchRunRequest(BaseModel):
    source: str = 'naver'


from __future__ import annotations

# 이 파일은 Data Status 화면과 배치 실행 API 응답을 조립한다.
from backend.app.repositories.batch_repository import BatchRepository
from backend.app.schemas.batch import BatchListResponse, BatchLogResponse, BatchTaskItem, PreviewResponse, RunAllState
from backend.app.services.view_helpers import time_ago
from backend.app.workers.batch_runner import runner


# 이 서비스는 배치 화면에 필요한 상태와 실행 동작을 묶는다.
class BatchService:
    def __init__(self, repository: BatchRepository | None = None) -> None:
        self.repository = repository or BatchRepository()

    # 이 메서드는 Data Status 카드 목록과 Run All 상태를 함께 반환한다.
    def get_batch_list(self) -> BatchListResponse:
        meta_rows = {row['task_id']: row for row in self.repository.fetch_batch_status_rows()}
        items: list[BatchTaskItem] = []
        for task_id, task in runner.tasks().items():
            task_state = runner.task_state(task_id)
            meta = meta_rows.get(task_id, {})
            status = 'RUNNING' if task_state['running'] else task_state['last_run_status']
            if status == 'IDLE':
                status = 'OK' if meta.get('updated_at') else 'MISSING'
            updated_at = meta.get('updated_at').isoformat() if meta.get('updated_at') else None
            run_date = meta.get('max_data_time').date().isoformat() if hasattr(meta.get('max_data_time'), 'date') else None
            items.append(
                BatchTaskItem(
                    id=task_id,
                    title=task['title'],
                    group=task['group'],
                    output_target=task['output_target'],
                    status=status,
                    running=bool(task_state['running']),
                    updated_at=updated_at,
                    updated_ago=time_ago(updated_at),
                    records=int(meta.get('records', 0) or 0),
                    run_date=run_date if task_id == 'ai_jongga_v2' else None,
                    reference_data_time=run_date,
                    source='db',
                    supported_sources=list(task.get('supported_sources', [])),
                    effective_source=runner.task_source(task_id),
                    started_at=task_state['last_run_started_at'],
                    finished_at=task_state['last_run_finished_at'],
                    exit_code=task_state['last_exit_code'],
                )
            )

        return BatchListResponse(tasks=items, run_all=RunAllState(**runner.run_all_state()))

    # 이 메서드는 단일 배치를 비동기로 시작한다.
    def start_task(self, task_id: str, source: str) -> bool:
        return runner.run_task_async(task_id, source)

    # 이 메서드는 Run All 을 비동기로 시작한다.
    def start_run_all(self, source: str) -> bool:
        return runner.run_all_async(source)

    # 이 메서드는 Preview 데이터를 반환한다.
    def get_preview(self, task_id: str, limit: int) -> PreviewResponse:
        columns, rows = self.repository.fetch_preview_rows(task_id, limit)
        return PreviewResponse(columns=columns, rows=rows)

    # 이 메서드는 로그 팝업에서 사용할 로그 응답을 반환한다.
    def get_logs(self, task_id: str) -> BatchLogResponse:
        task_state = runner.task_state(task_id)
        logs = runner.read_logs(task_id)
        return BatchLogResponse(
            task_id=task_id,
            status=task_state['last_run_status'],
            running=bool(task_state['running']),
            started_at=task_state['last_run_started_at'],
            finished_at=task_state['last_run_finished_at'],
            exit_code=task_state['last_exit_code'],
            stdout_tail=logs['stdout_tail'],
            stderr_tail=logs['stderr_tail'],
        )


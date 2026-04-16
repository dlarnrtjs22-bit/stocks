from __future__ import annotations

# 이 파일은 새 프로젝트에서 사용할 배치 실행기와 상태 레지스트리를 관리한다.
import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from backend.app.core.config import settings

COLLECTOR_SOURCES = {'naver', 'kiwoom'}


# 이 함수는 현재 시각을 ISO 문자열로 만든다.
def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


# 이 데이터 클래스는 배치 하나의 상태를 보관한다.
@dataclass(slots=True)
class TaskState:
    running: bool = False
    last_run_started_at: str | None = None
    last_run_finished_at: str | None = None
    last_exit_code: int | None = None
    last_run_status: str = 'IDLE'


# 이 데이터 클래스는 Run All 전체 상태를 보관한다.
@dataclass(slots=True)
class RunAllState:
    running: bool = False
    status: str = 'IDLE'
    started_at: str | None = None
    finished_at: str | None = None
    current_task: str | None = None
    completed_tasks: list[str] = field(default_factory=list)
    error_task: str | None = None
    error_message: str | None = None


# 이 클래스는 메모리 기반 배치 상태와 로그 파일 경로를 관리한다.
class BatchRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks = self._build_tasks()
        self._task_state: dict[str, TaskState] = {task_id: TaskState() for task_id in self._tasks}
        self._task_last_source: dict[str, str] = {
            task_id: str(task.get('default_source', 'naver'))
            for task_id, task in self._tasks.items()
        }
        self._run_all_state = RunAllState()

    # 이 메서드는 배치 정의를 새 프로젝트 기준으로 만든다.
    def _build_tasks(self) -> dict[str, dict[str, Any]]:
        python_exe = sys.executable
        runtime_root = settings.batch_runtime_root
        return {
            'daily_prices': {
                'id': 'daily_prices',
                'title': 'Daily Prices',
                'group': 'Closing Bet',
                'default_source': 'naver',
                'supported_sources': ['naver', 'kiwoom'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'pipelines' / 'naver_bootstrap_collect.py'), '--steps', 'universe,ohlcv,snapshot', '--limit-per-market', '100', '--days', '90'],
                    'kiwoom': [python_exe, str(runtime_root / 'pipelines' / 'kiwoom_bootstrap_collect.py'), '--steps', 'ohlcv,intraday,snapshot', '--limit-per-market', '100', '--intraday-top', '60'],
                },
                'output_target': 'db:public.naver_ohlcv_1d',
            },
            'institutional_trend': {
                'id': 'institutional_trend',
                'title': 'Institutional Trend',
                'group': 'Closing Bet',
                'default_source': 'naver',
                'supported_sources': ['naver', 'kiwoom'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'pipelines' / 'naver_bootstrap_collect.py'), '--steps', 'flows', '--flow-top', '90', '--flow-pages', '2'],
                    'kiwoom': [python_exe, str(runtime_root / 'pipelines' / 'kiwoom_bootstrap_collect.py'), '--steps', 'flows', '--limit-per-market', '100'],
                },
                'output_target': 'db:public.naver_flows_1d',
            },
            'ai_analysis': {
                'id': 'ai_analysis',
                'title': 'AI Analysis',
                'group': 'Closing Bet',
                'default_source': 'naver',
                'supported_sources': ['naver'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'pipelines' / 'naver_bootstrap_collect.py'), '--steps', 'news', '--news-top', '25', '--news-summary-top', '3'],
                },
                'output_target': 'db:public.naver_news_items',
            },
            'market_context': {
                'id': 'market_context',
                'title': 'Market Pulse',
                'group': 'Closing Bet',
                'default_source': 'naver',
                'supported_sources': ['naver'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'pipelines' / 'naver_bootstrap_collect.py'), '--steps', 'market'],
                },
                'output_target': 'db:public.naver_market_context_1d',
            },
            'program_trend': {
                'id': 'program_trend',
                'title': 'Program Trend',
                'group': 'Closing Bet',
                'default_source': 'naver',
                'supported_sources': ['naver', 'kiwoom'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'pipelines' / 'naver_bootstrap_collect.py'), '--steps', 'program'],
                    'kiwoom': [python_exe, str(runtime_root / 'pipelines' / 'kiwoom_bootstrap_collect.py'), '--steps', 'program'],
                },
                'output_target': 'db:public.naver_program_trend_1d',
            },
            'intraday_pressure': {
                'id': 'intraday_pressure',
                'title': 'Intraday Pressure',
                'group': 'Closing Bet',
                'default_source': 'kiwoom',
                'supported_sources': ['naver', 'kiwoom'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'pipelines' / 'kiwoom_bootstrap_collect.py'), '--steps', 'program,stock_program,intraday', '--intraday-top', '80'],
                    'kiwoom': [python_exe, str(runtime_root / 'pipelines' / 'kiwoom_bootstrap_collect.py'), '--steps', 'program,stock_program,intraday', '--intraday-top', '80'],
                },
                'output_target': 'db:public.kiwoom_intraday_feature_snapshots + public.kiwoom_program_snapshots + public.kiwoom_stock_program_*',
            },
            'vcp_signals': {
                'id': 'vcp_signals',
                'title': 'VCP Signals',
                'group': 'Closing Bet',
                'default_source': 'naver',
                'supported_sources': ['naver'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'pipelines' / 'build_vcp_signals.py'), '--top', '400'],
                },
                'output_target': 'db:public.naver_vcp_signals_latest',
            },
            'ai_jongga_v2': {
                'id': 'ai_jongga_v2',
                'title': 'AI Jongga V2',
                'group': 'Closing Bet',
                'default_source': 'naver',
                'supported_sources': ['naver', 'kiwoom'],
                'commands': {
                    'naver': [python_exe, str(runtime_root / 'run.py'), 'scan', '--capital', '50000000'],
                    'kiwoom': [python_exe, str(runtime_root / 'run.py'), 'scan', '--capital', '50000000'],
                },
                'output_target': 'db:public.jongga_runs + public.jongga_signals',
            },
        }

    def _normalize_source(self, source: str | None) -> str:
        normalized = str(source or 'naver').strip().lower()
        return normalized if normalized in COLLECTOR_SOURCES else 'naver'

    def _effective_source_for_task(self, task_id: str, source: str | None) -> str:
        task = self._tasks[task_id]
        normalized = self._normalize_source(source)
        supported = {str(item).strip().lower() for item in task.get('supported_sources', [])}
        if normalized in supported:
            return normalized
        return str(task.get('default_source', 'naver'))

    def _resolve_command(self, task_id: str, source: str | None) -> tuple[list[str], str]:
        task = self._tasks[task_id]
        effective_source = self._effective_source_for_task(task_id, source)
        commands = task.get('commands', {})
        command = list(commands.get(effective_source) or commands.get(task.get('default_source', 'naver')) or [])
        return command, effective_source

    def task_source(self, task_id: str) -> str:
        with self._lock:
            return self._task_last_source.get(task_id, str(self._tasks[task_id].get('default_source', 'naver')))

    # 이 메서드는 태스크 로그 파일 경로를 계산한다.
    def _log_path(self, task_id: str, stream_name: str) -> Path:
        return settings.runtime_logs_dir / f'{task_id}.{stream_name}.log'

    # 이 메서드는 현재 태스크 정의 목록을 반환한다.
    def tasks(self) -> dict[str, dict[str, Any]]:
        return self._tasks

    # 이 메서드는 Run All 상태를 사전 형태로 반환한다.
    def run_all_state(self) -> dict[str, Any]:
        with self._lock:
            state = self._run_all_state
            return {
                'running': state.running,
                'status': state.status,
                'started_at': state.started_at,
                'finished_at': state.finished_at,
                'current_task': state.current_task,
                'completed_tasks': list(state.completed_tasks),
                'error_task': state.error_task,
                'error_message': state.error_message,
            }

    # 이 메서드는 개별 태스크 상태를 사전 형태로 반환한다.
    def task_state(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._task_state[task_id]
            return {
                'running': state.running,
                'last_run_started_at': state.last_run_started_at,
                'last_run_finished_at': state.last_run_finished_at,
                'last_exit_code': state.last_exit_code,
                'last_run_status': state.last_run_status,
            }

    # 이 메서드는 저장된 로그 파일의 끝부분만 읽어 반환한다.
    def read_logs(self, task_id: str) -> dict[str, str]:
        def read_tail(path: Path) -> str:
            if not path.exists():
                return ''
            text = path.read_text(encoding='utf-8', errors='replace')
            return text[-12000:]

        return {
            'stdout_tail': read_tail(self._log_path(task_id, 'stdout')),
            'stderr_tail': read_tail(self._log_path(task_id, 'stderr')),
        }

    # 이 메서드는 백그라운드에서 개별 태스크를 실행한다.
    def run_task_async(self, task_id: str, source: str | None = None) -> bool:
        with self._lock:
            if self._run_all_state.running or self._task_state[task_id].running:
                return False
        threading.Thread(target=self._run_task_blocking, args=(task_id, source), daemon=True).start()
        return True

    # 이 메서드는 Run All 을 백그라운드에서 순차 실행한다.
    def run_all_async(self, source: str | None = None) -> bool:
        with self._lock:
            if self._run_all_state.running or any(item.running for item in self._task_state.values()):
                return False
        threading.Thread(target=self._run_all_blocking, args=(source,), daemon=True).start()
        return True

    # 이 메서드는 실제 하위 프로세스를 실행하고 상태를 갱신한다.
    def _run_task_blocking(self, task_id: str, source: str | None = None) -> None:
        task = self._tasks[task_id]
        command, effective_source = self._resolve_command(task_id, source)
        stdout_path = self._log_path(task_id, 'stdout')
        stderr_path = self._log_path(task_id, 'stderr')
        stdout_path.write_text('', encoding='utf-8')
        stderr_path.write_text('', encoding='utf-8')

        with self._lock:
            state = self._task_state[task_id]
            state.running = True
            state.last_run_started_at = iso_now()
            state.last_run_finished_at = None
            state.last_exit_code = None
            state.last_run_status = 'RUNNING'
            self._task_last_source[task_id] = effective_source

        child_env = os.environ.copy()
        child_env['PYTHONUNBUFFERED'] = '1'
        child_env['PYTHONPATH'] = os.pathsep.join(
            [
                str(settings.project_root / '.pydeps'),
                str(settings.project_root),
                str(settings.batch_runtime_root),
            ]
        )
        child_env['SUPABASE_SKIP_ENSURE_SCHEMA'] = '1'
        child_env['STORAGE_BACKEND'] = child_env.get('STORAGE_BACKEND', 'supabase')
        child_env['CHATGPT_OAUTH_TOKEN_FILE'] = str(settings.project_root / 'chatgptOauthKey.json')
        child_env['COLLECTOR_SOURCE'] = effective_source
        child_env.pop('CODEX_CHAT_UI_PYTHON_DIR', None)

        # 백엔드가 이미 사용 중인 DB 접속 URL을 배치 자식 프로세스에 그대로 전달한다.
        if settings.database_url:
            child_env['SUPABASE_DATABASE_URL'] = settings.database_url
            child_env['DATABASE_URL'] = settings.database_url

        # 로컬 .env 가 있을 경우 누락된 항목만 보완한다.
        env_path = settings.project_root / '.env'
        if env_path.exists():
            for key, value in dotenv_values(env_path).items():
                if key and value is not None and key not in child_env:
                    child_env[key] = str(value)

        exit_code = 1
        try:
            with stdout_path.open('w', encoding='utf-8') as stdout_file, stderr_path.open('w', encoding='utf-8') as stderr_file:
                process = subprocess.Popen(
                    command,
                    cwd=str(settings.batch_runtime_root),
                    env=child_env,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                )
                exit_code = process.wait()
        except Exception as exc:
            stderr_path.write_text(f'[runner error] {exc}\n', encoding='utf-8')
            exit_code = 1

        with self._lock:
            state = self._task_state[task_id]
            state.running = False
            state.last_run_finished_at = iso_now()
            state.last_exit_code = exit_code
            state.last_run_status = 'OK' if exit_code == 0 else 'ERROR'

    # 이 메서드는 Run All 을 순서대로 실행한다.
    def _run_all_blocking(self, source: str | None = None) -> None:
        order = list(self._tasks.keys())
        with self._lock:
            self._run_all_state = RunAllState(running=True, status='RUNNING', started_at=iso_now(), completed_tasks=[])

        for task_id in order:
            with self._lock:
                self._run_all_state.current_task = task_id
            self._run_task_blocking(task_id, source)
            state = self.task_state(task_id)
            with self._lock:
                self._run_all_state.completed_tasks.append(task_id)
                if state['last_run_status'] != 'OK':
                    self._run_all_state.running = False
                    self._run_all_state.status = 'ERROR'
                    self._run_all_state.finished_at = iso_now()
                    self._run_all_state.error_task = task_id
                    self._run_all_state.error_message = f"task '{task_id}' failed"
                    self._run_all_state.current_task = None
                    return

        with self._lock:
            self._run_all_state.running = False
            self._run_all_state.status = 'OK'
            self._run_all_state.finished_at = iso_now()
            self._run_all_state.current_task = None


# 이 객체는 앱 전역에서 공유하는 단일 배치 실행기다.
runner = BatchRunner()


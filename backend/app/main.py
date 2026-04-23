from __future__ import annotations

# 이 파일은 FastAPI 앱 생성과 시작/종료 훅을 담당한다.
import asyncio
import logging
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes.batches import router as batches_router
from backend.app.api.routes.closing_bet import router as closing_bet_router
from backend.app.api.routes.controls import router as controls_router
from backend.app.api.routes.dashboard import router as dashboard_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.history import router as history_router
from backend.app.api.routes.performance import router as performance_router
from backend.app.api.routes.trade_history import router as trade_history_router
from backend.app.core.config import settings
from backend.app.core.database import close_db_pool, open_db_pool
from backend.app.core.logging import configure_logging


logger = logging.getLogger(__name__)


# Design Ref: Design §1.1 — scheduler를 백엔드 내장 쓰레드로 상주
# 백엔드와 함께 항상 시동. 개별 job on/off, 전체 kill switch 는 UI(/control)에서 제어.
def _start_scheduler_thread(stop_event: threading.Event) -> threading.Thread | None:
    # batch/runtime_source 를 PYTHONPATH에 넣어야 scheduler.py 의 relative import 동작
    batch_root = settings.batch_runtime_root
    if str(batch_root) not in sys.path:
        sys.path.insert(0, str(batch_root))

    from batch.runtime_source import scheduler as sched_mod

    def _worker():
        logger.info('[scheduler] embedded thread starting')
        try:
            # 시그널 핸들러 없이 돌리고, stop_event로 중단 감지
            def _patched_run_loop():
                import time as _time
                from datetime import datetime as _dt
                from zoneinfo import ZoneInfo as _Zi
                SEOUL = _Zi('Asia/Seoul')
                logger.info('[scheduler] %d jobs registered', len(sched_mod.JOBS))
                for j in sched_mod.JOBS:
                    logger.info('[scheduler]   %-16s %s days=%s', j.name, j.fire_time, j.days)
                while not stop_event.is_set():
                    now = _dt.now(SEOUL)
                    today_str = now.date().isoformat()
                    for job in sched_mod.JOBS:
                        if job.last_run_date == today_str:
                            continue
                        if now.weekday() not in job.days:
                            continue
                        if now.hour == job.fire_time.hour and now.minute == job.fire_time.minute:
                            if sched_mod._is_job_disabled(job.name):
                                logger.info('[scheduler] SKIP(disabled): %s', job.name)
                                job.last_run_date = today_str
                                continue
                            logger.info('[scheduler] FIRE: %s @ %s', job.name, now.strftime('%H:%M:%S'))
                            try:
                                job.run()
                            except Exception as exc:
                                logger.exception('[scheduler] job failed %s: %s', job.name, exc)
                            job.last_run_date = today_str
                    stop_event.wait(30)  # 30초 폴링 (Event.wait이라 stop 시 즉시 깨어남)
                logger.info('[scheduler] stop_event set, exiting loop')
            _patched_run_loop()
        except Exception as exc:
            logger.exception('[scheduler] thread crashed: %s', exc)

    t = threading.Thread(target=_worker, name='stocks-scheduler', daemon=True)
    t.start()
    return t


# 이 lifespan 훅은 앱 시작 시 pool 과 read model 을 준비한다.
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(settings.project_root / '.env')
    configure_logging()
    await asyncio.to_thread(open_db_pool)
    # scheduler 시작
    stop_event = threading.Event()
    sched_thread = _start_scheduler_thread(stop_event)
    try:
        yield
    finally:
        if sched_thread is not None:
            logger.info('[scheduler] requesting stop...')
            stop_event.set()
            sched_thread.join(timeout=10)
        await asyncio.to_thread(close_db_pool)


# 이 함수는 프론트 빌드 결과가 있으면 FastAPI 가 정적 웹앱도 함께 제공하게 만든다.
def _mount_frontend(app: FastAPI) -> None:
    dist_dir = settings.project_root / 'frontend' / 'dist'
    assets_dir = dist_dir / 'assets'
    if not dist_dir.exists():
        return

    if assets_dir.exists():
        app.mount('/assets', StaticFiles(directory=str(assets_dir)), name='frontend-assets')

    @app.get('/', include_in_schema=False)
    def serve_frontend_root() -> FileResponse:
        return FileResponse(dist_dir / 'index.html')

    @app.get('/{file_path:path}', include_in_schema=False)
    def serve_frontend_file(file_path: str) -> FileResponse:
        if file_path.startswith('api/'):
            raise HTTPException(status_code=404, detail='not found')

        target = dist_dir / Path(file_path)
        if file_path and target.exists() and target.is_file():
            return FileResponse(target)

        return FileResponse(dist_dir / 'index.html')


# 이 함수는 새 프로젝트의 FastAPI 앱을 구성한다.
def create_app() -> FastAPI:
    app = FastAPI(title='stocks_new', version='0.1.0', lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f'http://127.0.0.1:{settings.frontend_port}',
            f'http://localhost:{settings.frontend_port}',
        ],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.include_router(health_router)
    app.include_router(dashboard_router)
    app.include_router(trade_history_router)
    app.include_router(closing_bet_router)
    app.include_router(performance_router)
    app.include_router(batches_router)
    app.include_router(controls_router)
    app.include_router(history_router)
    _mount_frontend(app)
    return app


# 이 객체가 실제 Uvicorn 에서 불러가는 FastAPI 앱 인스턴스다.
app = create_app()

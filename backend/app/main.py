from __future__ import annotations

# 이 파일은 FastAPI 앱 생성과 시작/종료 훅을 담당한다.
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes.batches import router as batches_router
from backend.app.api.routes.closing_bet import router as closing_bet_router
from backend.app.api.routes.dashboard import router as dashboard_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.performance import router as performance_router
from backend.app.api.routes.trade_history import router as trade_history_router
from backend.app.core.config import settings
from backend.app.core.database import close_db_pool, open_db_pool
from backend.app.core.logging import configure_logging


# 이 lifespan 훅은 앱 시작 시 pool 과 read model 을 준비한다.
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(settings.project_root / '.env')
    configure_logging()
    open_db_pool()
    try:
        yield
    finally:
        close_db_pool()


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
    _mount_frontend(app)
    return app


# 이 객체가 실제 Uvicorn 에서 불러가는 FastAPI 앱 인스턴스다.
app = create_app()

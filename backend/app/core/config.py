from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(slots=True)
class Settings:
    app_host: str
    app_port: int
    frontend_port: int
    project_root: Path
    batch_runtime_root: Path
    runtime_logs_dir: Path
    database_url: str
    db_pool_min_size: int
    db_pool_max_size: int
    db_pool_timeout: int


def _build_database_url() -> str:
    direct_url = str(os.getenv('SUPABASE_DATABASE_URL', '') or os.getenv('DATABASE_URL', '')).strip()
    if direct_url:
        return direct_url

    host = str(os.getenv('SUPABASE_DB_HOST', 'localhost')).strip()
    port = str(os.getenv('SUPABASE_DB_PORT', '5432')).strip()
    db_name = str(os.getenv('SUPABASE_DB_NAME', 'stocks')).strip()
    user = str(os.getenv('SUPABASE_DB_USER', 'postgres')).strip()
    password = str(os.getenv('SUPABASE_DB_PASSWORD', ''))
    return f"postgresql://{user}:{quote(password, safe='')}@{host}:{port}/{db_name}"


def load_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[3]
    batch_runtime_root = project_root / 'batch' / 'runtime_source'
    runtime_logs_dir = project_root / 'runtime' / 'logs'
    runtime_logs_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        app_host=str(os.getenv('APP_HOST', '127.0.0.1')).strip(),
        app_port=int(str(os.getenv('APP_PORT', '5056')).strip()),
        frontend_port=int(str(os.getenv('FRONTEND_PORT', '5173')).strip()),
        project_root=project_root,
        batch_runtime_root=batch_runtime_root,
        runtime_logs_dir=runtime_logs_dir,
        database_url=_build_database_url(),
        db_pool_min_size=int(str(os.getenv('DB_POOL_MIN_SIZE', '1')).strip()),
        db_pool_max_size=int(str(os.getenv('DB_POOL_MAX_SIZE', '10')).strip()),
        db_pool_timeout=int(str(os.getenv('DB_POOL_TIMEOUT', '30')).strip()),
    )


settings = load_settings()

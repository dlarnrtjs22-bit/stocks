from __future__ import annotations

# 이 파일은 psycopg_pool 기반의 DB 연결 풀을 관리한다.
from contextlib import contextmanager
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.app.core.config import settings


# 이 전역 변수는 앱 시작 시 열리는 DB 연결 풀을 담는다.
_POOL: ConnectionPool | None = None


# 이 함수는 SQL 파일을 읽어 문자열로 반환한다.
def _read_sql_file(path: Path) -> str:
    return path.read_text(encoding='utf-8').strip()


# 이 함수는 앱 시작 시 DB 풀을 만들고 read model SQL도 함께 반영한다.
def open_db_pool() -> None:
    global _POOL
    if _POOL is not None:
        return

    _POOL = ConnectionPool(
        conninfo=settings.database_url,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        timeout=float(settings.db_pool_timeout),
        kwargs={
            'autocommit': True,
            'row_factory': dict_row,
        },
    )
    _POOL.open(wait=True)
    apply_read_models()


# 이 함수는 앱 종료 시 DB 풀을 정상적으로 닫는다.
def close_db_pool() -> None:
    global _POOL
    if _POOL is None:
        return
    _POOL.close()
    _POOL = None


# 이 함수는 현재 열린 DB 풀을 반환한다.
def get_db_pool() -> ConnectionPool:
    if _POOL is None:
        raise RuntimeError('DB pool is not initialized')
    return _POOL


# 이 컨텍스트 매니저는 요청 단위로 커넥션을 빌려 쓰게 한다.
@contextmanager
def db_connection():
    with get_db_pool().connection() as conn:
        yield conn


# 이 함수는 새 프로젝트의 조회용 view 와 인덱스를 DB에 반영한다.
def apply_read_models() -> None:
    sql_dir = settings.project_root / 'backend' / 'app' / 'sql'
    statements = [
        _read_sql_file(sql_dir / 'kiwoom.sql'),
        _read_sql_file(sql_dir / 'indexes.sql'),
        _read_sql_file(sql_dir / 'views.sql'),
    ]
    with db_connection() as conn:
        with conn.cursor() as cur:
            for sql in statements:
                if not sql:
                    continue
                cur.execute(sql)


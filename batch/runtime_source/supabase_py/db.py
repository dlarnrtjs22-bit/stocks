from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import quote

import psycopg


DEFAULT_SUPABASE_HOST = "localhost"
DEFAULT_SUPABASE_PORT = "5432"
DEFAULT_SUPABASE_DB = "stocks"
DEFAULT_SUPABASE_USER = "postgres"
DEFAULT_SUPABASE_PASSWORD = ""


def storage_backend() -> str:
    return str(os.getenv("STORAGE_BACKEND", "supabase")).strip().lower() or "supabase"


def is_supabase_backend() -> bool:
    return storage_backend() in {"supabase", "postgres", "postgresql", "db"}


def _fallback_database_url() -> str:
    host = str(os.getenv("SUPABASE_DB_HOST", "") or DEFAULT_SUPABASE_HOST).strip()
    port = str(os.getenv("SUPABASE_DB_PORT", "") or DEFAULT_SUPABASE_PORT).strip()
    dbname = str(os.getenv("SUPABASE_DB_NAME", "") or DEFAULT_SUPABASE_DB).strip()
    user = str(os.getenv("SUPABASE_DB_USER", "") or DEFAULT_SUPABASE_USER).strip()
    password_raw = str(os.getenv("SUPABASE_DB_PASSWORD", "") or DEFAULT_SUPABASE_PASSWORD)

    if not host or not port or not dbname or not user:
        return ""

    password = quote(password_raw, safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def get_database_url() -> str:
    url = str(os.getenv("SUPABASE_DATABASE_URL", "")).strip()
    if not url:
        url = str(os.getenv("DATABASE_URL", "")).strip()
    if not url and is_supabase_backend():
        url = _fallback_database_url()
        if url:
            os.environ["SUPABASE_DATABASE_URL"] = url
    if not url:
        raise RuntimeError("SUPABASE_DATABASE_URL (or DATABASE_URL) is required for DB backend")
    return url


@contextmanager
def get_conn(autocommit: bool = False) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(get_database_url(), autocommit=autocommit)
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()

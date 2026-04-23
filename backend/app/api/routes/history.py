"""실행 히스토리 API.

하루에 한 row 씩 누적되는 daily_execution_history 를 페이지네이션으로 조회.

엔드포인트:
  GET /api/history/list?page=1&page_size=20
  GET /api/history/{date}         (YYYY-MM-DD)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.core.database import db_connection


router = APIRouter(prefix="/api/history", tags=["history"])


def _row_to_dict(row: dict, *, include_events: bool = False) -> dict[str, Any]:
    d = {
        "history_date": row.get("history_date").isoformat() if row.get("history_date") else None,
        "title": row.get("title") or "",
        "summary": row.get("summary") or "",
        "event_count": int(row.get("event_count") or 0),
        "version": int(row.get("version") or 1),
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }
    if include_events:
        d["content"] = row.get("content") or ""
        d["events"] = row.get("events_json") or []
    return d


@router.get("/list")
def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """날짜 내림차순 목록."""
    offset = (page - 1) * page_size
    items: list[dict[str, Any]] = []
    total = 0
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM daily_execution_history")
                total = int((cur.fetchone() or {}).get("n") or 0)
                cur.execute(
                    """
                    SELECT history_date, title, summary, event_count, version, updated_at
                    FROM daily_execution_history
                    ORDER BY history_date DESC
                    LIMIT %s OFFSET %s
                    """,
                    (page_size, offset),
                )
                for r in cur.fetchall():
                    items.append(_row_to_dict(r, include_events=False))
    except Exception as exc:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0, "error": str(exc)}

    total_pages = (total + page_size - 1) // page_size if total else 0
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.get("/{target_date}")
def get_history(target_date: str) -> dict[str, Any]:
    """단일 날짜 상세 (content + events)."""
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT history_date, title, summary, content, events_json, event_count, version, updated_at
                    FROM daily_execution_history
                    WHERE history_date = %s
                    """,
                    (target_date,),
                )
                row = cur.fetchone()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail=f"no history for {target_date}")
    return _row_to_dict(row, include_events=True)

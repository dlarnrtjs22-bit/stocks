"""일별 실행 히스토리 게시판 이벤트 수집.

하루에 한 row(daily_execution_history)를 유지하고, 시점별 이벤트를 events_json에
append한다. content 는 LLM (기본) 또는 템플릿 fallback 으로 재생성한다.

사용:
    from batch.runtime_source.utils.execution_history import record_event
    record_event(
        event_type="candidate_extract",
        summary="Top 2 후보 저장 (005930 외 1종목)",
        details={"picked_count": 2, "tickers": ["005930", "373220"]},
    )

이벤트 타입 (표준):
    candidate_extract   15:30 후보 저장 완료
    briefing            19:30/19:40 장후 브리핑 판정
    buy_tranche         19:50/54/58 각 tranche 주문 결과
    buy_skip            매수 스킵 (가드/DROP/후보없음 등)
    sell_tranche        익일 08:00~ 매도 주문 결과
    sell_skip           매도 스킵
    pnl_reconcile       09:10 P/L 집계
    system_note         수동/외부 기록

환경변수:
    EXECUTION_HISTORY_LLM    "1" 이면 LLM 요약 사용 (default). "0" 이면 템플릿만.
    EXECUTION_HISTORY_LLM_EFFORT   low / medium / high (default: low)

DB 실패는 호출부를 막지 않는다 (try/except 로 삼킴).
LLM 실패 시 자동으로 템플릿 fallback.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SEOUL_TZ = ZoneInfo("Asia/Seoul")
PROJECT_ROOT = Path(__file__).resolve().parents[3]


EVENT_LABEL = {
    "candidate_extract": "15:30 후보 추출",
    "briefing":          "장후 브리핑",
    "buy_tranche":       "매수 tranche",
    "buy_skip":          "매수 스킵",
    "sell_tranche":      "매도 tranche",
    "sell_skip":         "매도 스킵",
    "pnl_reconcile":     "일일 P/L 집계",
    "system_note":       "시스템 기록",
}


def _now_seoul() -> datetime:
    return datetime.now(SEOUL_TZ)


def _format_content_template(events: list[dict[str, Any]]) -> tuple[str, str]:
    """템플릿 기반 fallback (LLM 실패 시 사용).
    반환: (summary 한 줄, content 전체 본문)
    """
    if not events:
        return "기록 없음", "아직 기록된 이벤트가 없습니다."

    sorted_events = sorted(events, key=lambda e: str(e.get("ts", "")))
    lines: list[str] = []
    highlights: list[str] = []

    for e in sorted_events:
        ts = str(e.get("ts", ""))
        time_part = ts[11:16] if len(ts) >= 16 else ts  # HH:MM
        etype = str(e.get("event_type", "system_note"))
        label = EVENT_LABEL.get(etype, etype)
        summary = str(e.get("summary", "")).strip()
        details = e.get("details") or {}
        lines.append(f"[{time_part}] {label} — {summary}")
        if details:
            for k, v in details.items():
                if v is None or v == "":
                    continue
                if isinstance(v, (list, dict)):
                    v_str = json.dumps(v, ensure_ascii=False, default=str)
                else:
                    v_str = str(v)
                if len(v_str) > 200:
                    v_str = v_str[:200] + "…"
                lines.append(f"    - {k}: {v_str}")
        # 하이라이트 추출
        if etype in ("candidate_extract", "buy_tranche", "sell_tranche", "pnl_reconcile"):
            highlights.append(f"{label}({time_part}) {summary}")
        if etype in ("buy_skip", "sell_skip") and summary:
            highlights.append(f"⚠ {label}({time_part}) {summary}")

    summary_line = " / ".join(highlights[:3]) if highlights else sorted_events[-1].get("summary", "")
    if len(summary_line) > 280:
        summary_line = summary_line[:277] + "…"
    content = "\n".join(lines)
    return summary_line, content


def _build_llm_prompt(events: list[dict[str, Any]]) -> str:
    return (
        "너는 한국 주식 NXT 종가배팅 자동매매 시스템의 일별 실행 기록을 사람이 읽기 좋게 정리하는 역할이다.\n"
        "아래 이벤트들을 시간순으로 읽고 트레이더가 한눈에 파악할 수 있게 써라.\n"
        "\n[이벤트 원본, 시간순, JSON]\n"
        f"{json.dumps(events, ensure_ascii=False, default=str)}\n"
        "\n[요구사항]\n"
        "- summary: 1~2줄. 오늘 매매가 어떻게 됐는지 핵심만 (매수 성공/스킵/매도/P&L 등). 280자 이내.\n"
        "- content: 시간순 마크다운 내러티브. 각 이벤트를 자연스럽게 연결.\n"
        "  · 시각은 'HH:MM' 표기\n"
        "  · 종목코드는 종목명 병기 (예: 005930 삼성전자)\n"
        "  · 숫자 천단위 쉼표\n"
        "  · 스킵/실패가 있으면 원인을 짚어주고, 설계 의도(CAUTION→B강등, DROP, paper 모드 등)를 간략히 설명\n"
        "  · 마지막에 한 줄 요약 (오늘 결과 총평)\n"
        "\n[응답 형식 — 반드시 JSON, 다른 설명 금지]\n"
        '{"summary":"...","content":"..."}\n'
    )


def _llm_summarize(events: list[dict[str, Any]]) -> tuple[str, str] | None:
    """LLM 으로 summary/content 재생성. 실패 시 None.

    chatgpt.py (프로젝트 로컬, OAuth 기반 기본 Codex 모델) 를 effort=low 로 호출.
    """
    if os.getenv("EXECUTION_HISTORY_LLM", "1").strip() in {"0", "false", "no", "off"}:
        return None
    try:
        import asyncio as _aio
        import sys as _sys

        if str(PROJECT_ROOT) not in _sys.path:
            _sys.path.insert(0, str(PROJECT_ROOT))
        from chatgpt import send_codex_message, DEFAULT_CODEX_MODEL

        effort = os.getenv("EXECUTION_HISTORY_LLM_EFFORT", "low").strip().lower() or "low"
        if effort not in {"low", "medium", "high", "xhigh"}:
            effort = "low"

        prompt = _build_llm_prompt(events)

        async def _run() -> str:
            acc = ""
            async for line in send_codex_message(
                conversation_history=[{"role": "user", "content": prompt}],
                model=DEFAULT_CODEX_MODEL,
                instructions="한국 주식 자동매매 시스템의 일별 로그를 요약하는 어시스턴트. 반드시 JSON 만 반환.",
                reasoning_effort=effort,
            ):
                if not str(line).startswith("data: "):
                    continue
                payload = str(line)[6:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    parsed = json.loads(payload)
                except Exception:
                    continue
                etype = parsed.get("type")
                if etype == "response.output_text.delta":
                    acc += str(parsed.get("delta", "") or "")
                elif etype == "response.output_text.done":
                    text = str(parsed.get("text", "") or "")
                    if text:
                        acc = text
            return acc.strip()

        raw = _aio.run(_run())
        if not raw:
            return None

        # 코드펜스 제거
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.find("\n")
            last_fence = cleaned.rfind("```")
            if first_nl > 0 and last_fence > first_nl:
                cleaned = cleaned[first_nl + 1:last_fence].strip()

        try:
            data = json.loads(cleaned)
            summary = str(data.get("summary") or "").strip()
            content = str(data.get("content") or "").strip()
            if summary and content:
                if len(summary) > 280:
                    summary = summary[:277] + "…"
                return summary, content
        except Exception:
            # JSON 파싱 실패 시 raw 텍스트를 content 로 간주
            preview = cleaned[:277] + "…" if len(cleaned) > 280 else cleaned
            if cleaned:
                return preview.split("\n", 1)[0][:280], cleaned

        return None
    except Exception as exc:
        print(f"[execution_history] LLM 요약 실패, 템플릿 fallback: {exc}")
        return None


def _format_content(events: list[dict[str, Any]]) -> tuple[str, str]:
    """LLM 우선, 실패 시 템플릿. 반환: (summary, content)."""
    if not events:
        return "기록 없음", "아직 기록된 이벤트가 없습니다."
    llm = _llm_summarize(events)
    if llm is not None:
        return llm
    return _format_content_template(events)


def record_event(
    *,
    event_type: str,
    summary: str,
    details: dict[str, Any] | None = None,
    target_date: str | None = None,
) -> bool:
    """오늘자 daily_execution_history 에 이벤트 1건 append + content 재생성.

    반환: 성공 여부 (실패해도 예외 던지지 않음).
    """
    try:
        from backend.app.core.database import db_connection

        now = _now_seoul()
        iso_ts = now.astimezone(timezone.utc).isoformat()
        date_str = target_date or now.date().isoformat()
        new_event = {
            "ts": iso_ts,
            "event_type": event_type,
            "summary": summary,
            "details": details or {},
        }

        with db_connection() as conn:
            with conn.cursor() as cur:
                # 기존 events_json 읽기 (없으면 새로 만듦)
                cur.execute(
                    "SELECT events_json, version FROM daily_execution_history WHERE history_date = %s",
                    (date_str,),
                )
                row = cur.fetchone()
                if row is None:
                    events = [new_event]
                    version = 1
                else:
                    raw = row.get("events_json") or []
                    events = list(raw) if isinstance(raw, list) else []
                    events.append(new_event)
                    version = int(row.get("version") or 1) + 1

                summary_line, content = _format_content(events)
                title = f"{date_str} 실행 히스토리"

                cur.execute(
                    """
                    INSERT INTO daily_execution_history
                      (history_date, title, summary, content, events_json, event_count, version, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (history_date) DO UPDATE SET
                      title=EXCLUDED.title,
                      summary=EXCLUDED.summary,
                      content=EXCLUDED.content,
                      events_json=EXCLUDED.events_json,
                      event_count=EXCLUDED.event_count,
                      version=EXCLUDED.version,
                      updated_at=NOW()
                    """,
                    (
                        date_str, title, summary_line, content,
                        json.dumps(events, ensure_ascii=False, default=str),
                        len(events), version,
                    ),
                )
        return True
    except Exception as exc:
        print(f"[execution_history] record 실패 ({event_type}): {exc}")
        return False

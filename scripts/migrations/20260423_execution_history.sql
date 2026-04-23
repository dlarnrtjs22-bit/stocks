-- Migration 20260423: 일별 실행 히스토리 게시판
-- 한 날짜당 한 row. events_json 에 시점별 원본 이벤트 append, content 는 템플릿 기반 요약.

CREATE TABLE IF NOT EXISTS daily_execution_history (
    history_date  DATE         PRIMARY KEY,
    title         VARCHAR(128) NOT NULL,
    summary       VARCHAR(320) NOT NULL DEFAULT '',
    content       TEXT         NOT NULL DEFAULT '',
    events_json   JSONB        NOT NULL DEFAULT '[]'::jsonb,
    event_count   INTEGER      NOT NULL DEFAULT 0,
    version       INTEGER      NOT NULL DEFAULT 1,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_execution_history_updated
    ON daily_execution_history(updated_at DESC);

-- Migration 20260423: 자동매매 누락 테이블 + 중복 방지
-- Design Ref: Plan §7-8 + controls.py + runner_sell.py + daily_pnl_reconcile.py + guards.py

-- ─── auto_orders ─────────────────────────────────────
-- trade_executor 가 매수/매도 주문 발주 시 기록. runner_sell/daily_pnl_reconcile/controls 가 조회.
CREATE TABLE IF NOT EXISTS auto_orders (
    order_id              VARCHAR(64)  PRIMARY KEY,
    set_date              DATE         NOT NULL,
    stock_code            VARCHAR(12)  NOT NULL,
    side                  VARCHAR(8)   NOT NULL,               -- BUY / SELL
    tranche               VARCHAR(16),                          -- T1/T2/T3/S0/S1/...
    venue                 VARCHAR(8)   NOT NULL DEFAULT 'NXT',
    order_type            VARCHAR(24)  NOT NULL,                -- LIMIT / LIMIT_MAKER / LIMIT_TAKER / MARKET_IOC
    price                 NUMERIC(18,2) NOT NULL DEFAULT 0,
    qty                   INTEGER      NOT NULL DEFAULT 0,
    status                VARCHAR(16)  NOT NULL DEFAULT 'PENDING',  -- PENDING/FILLED/PARTIAL/CANCELLED/FAILED
    filled_qty            INTEGER      NOT NULL DEFAULT 0,
    filled_avg_price      NUMERIC(18,2) NOT NULL DEFAULT 0,
    requested_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    filled_at             TIMESTAMPTZ,
    paper_mode            BOOLEAN      NOT NULL DEFAULT FALSE,
    error_msg             TEXT,
    idempotency_key       VARCHAR(64)  UNIQUE,
    note                  TEXT
);

CREATE INDEX IF NOT EXISTS idx_auto_orders_set_date         ON auto_orders(set_date);
CREATE INDEX IF NOT EXISTS idx_auto_orders_stock_code       ON auto_orders(stock_code);
CREATE INDEX IF NOT EXISTS idx_auto_orders_side_status      ON auto_orders(side, status);


-- ─── daily_pnl ─────────────────────────────────────
-- daily_pnl_reconcile 가 INSERT, guards.daily_loss_exceeded 가 SELECT.
CREATE TABLE IF NOT EXISTS daily_pnl (
    pnl_date          DATE         PRIMARY KEY,
    gross_buy_krw     BIGINT       NOT NULL DEFAULT 0,
    gross_sell_krw    BIGINT       NOT NULL DEFAULT 0,
    realized_pnl_krw  BIGINT       NOT NULL DEFAULT 0,
    realized_pct      NUMERIC(8,4) NOT NULL DEFAULT 0,
    cumulative_pct    NUMERIC(8,4) NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ─── candidate_set_v3 중복 방지 ─────────────────────
-- 같은 날 같은 종목을 여러 번 INSERT 방지. extract 재실행 시 upsert.
-- 먼저 기존 중복 정리 (같은 (set_date, stock_code) 중 최신 created_at 만 남김).
WITH dups AS (
    SELECT ctid, set_date, stock_code, created_at,
           ROW_NUMBER() OVER (PARTITION BY set_date, stock_code ORDER BY created_at DESC) AS rn
    FROM candidate_set_v3
)
DELETE FROM candidate_set_v3 c
USING dups d
WHERE c.ctid = d.ctid AND d.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_set_v3_date_code
    ON candidate_set_v3(set_date, stock_code);

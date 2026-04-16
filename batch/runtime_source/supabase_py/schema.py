from __future__ import annotations

from supabase_py.db import get_conn


DDL_STATEMENTS = [
    """
    create table if not exists naver_universe (
      ticker text primary key,
      name text not null,
      market text,
      market_cap_eok bigint,
      raw_volume bigint,
      updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists naver_ohlcv_1d (
      trade_date date not null,
      ticker text not null,
      open_price numeric,
      high_price numeric,
      low_price numeric,
      close_price numeric,
      volume bigint,
      trading_value bigint,
      foreign_retention_rate numeric,
      updated_at timestamptz not null default now(),
      primary key (trade_date, ticker)
    )
    """,
    """
    create table if not exists naver_flows_1d (
      trade_date date not null,
      ticker text not null,
      foreign_net_buy bigint,
      inst_net_buy bigint,
      retail_net_buy bigint,
      updated_at timestamptz not null default now(),
      primary key (trade_date, ticker)
    )
    """,
    """
    create table if not exists naver_news_items (
      id bigint generated always as identity primary key,
      ticker text not null,
      name text,
      published_at timestamptz,
      title text not null,
      summary text,
      source text,
      url text,
      relevance_score numeric,
      is_fallback boolean not null default false,
      updated_at timestamptz not null default now(),
      unique (ticker, title, published_at, url)
    )
    """,
    """
    create table if not exists naver_latest_snapshot (
      trade_date date not null,
      ticker text not null,
      name text,
      market text,
      close_price numeric,
      change_pct numeric,
      volume bigint,
      trading_value bigint,
      market_cap_eok bigint,
      updated_at timestamptz not null default now(),
      primary key (trade_date, ticker)
    )
    """,
    """
    create table if not exists naver_market_context_1d (
      trade_date date not null,
      market text not null,
      market_label text,
      market_status text,
      index_value numeric,
      change_pct numeric,
      rise_count integer,
      steady_count integer,
      fall_count integer,
      upper_count integer,
      lower_count integer,
      snapshot_time timestamptz,
      updated_at timestamptz not null default now(),
      primary key (trade_date, market)
    )
    """,
    """
    create table if not exists naver_program_trend_1d (
      trade_date date not null,
      market text not null,
      market_status text,
      arbitrage_buy bigint,
      arbitrage_sell bigint,
      arbitrage_net bigint,
      non_arbitrage_buy bigint,
      non_arbitrage_sell bigint,
      non_arbitrage_net bigint,
      total_buy bigint,
      total_sell bigint,
      total_net bigint,
      snapshot_time timestamptz,
      updated_at timestamptz not null default now(),
      primary key (trade_date, market)
    )
    """,
    """
    create table if not exists naver_vcp_signals_latest (
      trade_date date not null,
      ticker text not null,
      signal text,
      vcp_score numeric,
      close_price numeric,
      volume bigint,
      ma20 numeric,
      vol_ratio numeric,
      updated_at timestamptz not null default now(),
      primary key (trade_date, ticker)
    )
    """,
    """
    create table if not exists kiwoom_intraday_features_latest (
      trade_date date not null,
      ticker text not null,
      stock_name text,
      market text,
      venue text,
      current_price numeric,
      change_pct numeric,
      bid_total bigint,
      ask_total bigint,
      orderbook_imbalance numeric,
      execution_strength numeric,
      tick_volume bigint,
      minute_pattern text,
      minute_breakout_score numeric,
      volume_surge_ratio numeric,
      orderbook_surge_ratio numeric,
      vi_active boolean not null default false,
      vi_type text,
      condition_hit_count integer not null default 0,
      condition_names jsonb not null default '[]'::jsonb,
      acc_trade_value bigint,
      acc_trade_volume bigint,
      updated_at timestamptz not null default now(),
      primary key (trade_date, ticker)
    )
    """,
    """
    create table if not exists kiwoom_intraday_feature_snapshots (
      trade_date date not null,
      snapshot_time timestamptz not null,
      ticker text not null,
      stock_name text,
      market text,
      venue text,
      current_price numeric,
      change_pct numeric,
      bid_total bigint,
      ask_total bigint,
      orderbook_imbalance numeric,
      execution_strength numeric,
      tick_volume bigint,
      minute_pattern text,
      minute_breakout_score numeric,
      volume_surge_ratio numeric,
      orderbook_surge_ratio numeric,
      vi_active boolean not null default false,
      vi_type text,
      condition_hit_count integer not null default 0,
      condition_names jsonb not null default '[]'::jsonb,
      acc_trade_value bigint,
      acc_trade_volume bigint,
      updated_at timestamptz not null default now(),
      primary key (snapshot_time, ticker)
    )
    """,
    """
    create table if not exists kiwoom_condition_hits (
      trade_date date not null,
      ticker text not null,
      condition_seq text not null,
      condition_name text not null,
      hit_count integer not null default 1,
      first_seen_at timestamptz,
      last_seen_at timestamptz,
      updated_at timestamptz not null default now(),
      primary key (trade_date, ticker, condition_seq)
    )
    """,
    """
    create table if not exists kiwoom_program_snapshots (
      trade_date date not null,
      snapshot_time timestamptz not null,
      market text not null,
      market_status text,
      arbitrage_buy bigint,
      arbitrage_sell bigint,
      arbitrage_net bigint,
      non_arbitrage_buy bigint,
      non_arbitrage_sell bigint,
      non_arbitrage_net bigint,
      total_buy bigint,
      total_sell bigint,
      total_net bigint,
      updated_at timestamptz not null default now(),
      primary key (snapshot_time, market)
    )
    """,
    """
    create table if not exists kiwoom_account_snapshot_latest (
      account_no text primary key,
      snapshot_time timestamptz,
      venue text,
      total_purchase_amt bigint,
      total_eval_amt bigint,
      total_eval_profit bigint,
      total_profit_rate numeric,
      estimated_assets bigint,
      holdings_count integer,
      realized_profit bigint,
      unfilled_count integer,
      total_unfilled_qty bigint,
      avg_fill_latency_ms numeric,
      est_slippage_bps numeric,
      raw_payload jsonb not null default '{}'::jsonb,
      updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists kiwoom_account_positions_latest (
      account_no text not null,
      ticker text not null,
      stock_name text,
      quantity bigint,
      available_qty bigint,
      avg_price numeric,
      current_price numeric,
      eval_amount bigint,
      profit_amount bigint,
      profit_rate numeric,
      updated_at timestamptz not null default now(),
      primary key (account_no, ticker)
    )
    """,
    """
    create table if not exists kiwoom_order_execution_events (
      account_no text not null,
      order_no text not null,
      ticker text,
      stock_name text,
      order_type text,
      order_status text,
      order_qty bigint,
      filled_qty bigint,
      unfilled_qty bigint,
      order_price numeric,
      filled_price numeric,
      order_time timestamptz,
      filled_time timestamptz,
      fill_latency_ms numeric,
      slippage_bps numeric,
      venue text,
      raw_payload jsonb not null default '{}'::jsonb,
      updated_at timestamptz not null default now(),
      primary key (account_no, order_no)
    )
    """,
    """
    create table if not exists dashboard_cache_latest (
      cache_key text primary key,
      payload jsonb not null,
      updated_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists jongga_runs (
      run_id uuid primary key,
      run_date date not null,
      total_candidates integer not null,
      filtered_count integer not null,
      by_grade jsonb not null,
      by_market jsonb not null,
      runtime_meta jsonb not null,
      processing_time_ms double precision not null,
      source text not null default 'run_screener',
      created_at timestamptz not null default now()
    )
    """,
    """
    create table if not exists jongga_signals (
      run_id uuid not null references jongga_runs(run_id) on delete cascade,
      run_date date not null,
      signal_rank integer not null,
      stock_code text not null,
      stock_name text,
      market text,
      sector text,
      signal_date date,
      signal_time timestamptz,
      grade text,
      score jsonb not null,
      checklist jsonb not null,
      news_items jsonb not null,
      ai_overall jsonb not null,
      foreign_5d bigint,
      inst_5d bigint,
      individual_5d bigint,
      current_price numeric,
      entry_price numeric,
      stop_price numeric,
      target_price numeric,
      r_value numeric,
      position_size numeric,
      quantity integer,
      r_multiplier numeric,
      trading_value bigint,
      change_pct numeric,
      status text,
      created_at timestamptz,
      primary key (run_id, signal_rank)
    )
    """,
    "create index if not exists idx_ohlcv_ticker_date on naver_ohlcv_1d(ticker, trade_date desc)",
    "create index if not exists idx_flows_ticker_date on naver_flows_1d(ticker, trade_date desc)",
    "create index if not exists idx_news_ticker_time on naver_news_items(ticker, published_at desc)",
    "create index if not exists idx_snapshot_ticker_date on naver_latest_snapshot(ticker, trade_date desc)",
    "create index if not exists idx_market_context_date on naver_market_context_1d(trade_date desc, market)",
    "create index if not exists idx_program_trend_date on naver_program_trend_1d(trade_date desc, market)",
    "create index if not exists idx_kiwoom_intraday_trade_date on kiwoom_intraday_features_latest(trade_date desc, market, ticker)",
    "create index if not exists idx_kiwoom_intraday_snapshots_trade_time on kiwoom_intraday_feature_snapshots(trade_date desc, snapshot_time desc, ticker)",
    "create index if not exists idx_kiwoom_condition_hits_trade_date on kiwoom_condition_hits(trade_date desc, ticker)",
    "create index if not exists idx_kiwoom_program_snapshots_trade_time on kiwoom_program_snapshots(trade_date desc, snapshot_time desc, market)",
    "create index if not exists idx_kiwoom_positions_account on kiwoom_account_positions_latest(account_no, updated_at desc)",
    "create index if not exists idx_kiwoom_orders_account on kiwoom_order_execution_events(account_no, updated_at desc)",
    "create index if not exists idx_jongga_runs_date_created on jongga_runs(run_date desc, created_at desc)",
    "create index if not exists idx_jongga_signals_date_rank on jongga_signals(run_date desc, signal_rank asc)",
]


def ensure_schema() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            for ddl in DDL_STATEMENTS:
                cur.execute(ddl)

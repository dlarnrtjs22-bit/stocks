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
);

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
);

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
);

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
);

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
);

create table if not exists jongga_tracked_picks (
  tracked_id bigint generated always as identity primary key,
  run_id uuid not null references jongga_runs(run_id) on delete cascade,
  run_date date not null,
  featured_rank integer not null,
  signal_rank integer not null,
  stock_code text not null,
  stock_name text,
  market text,
  grade text,
  base_grade text,
  entry_price numeric,
  score_total integer not null default 0,
  selected_at timestamptz not null default now(),
  unique (run_id, stock_code)
);

create table if not exists jongga_compare_prices (
  tracked_id bigint not null references jongga_tracked_picks(tracked_id) on delete cascade,
  eval_date date not null,
  eval_slot text not null,
  venue text,
  price numeric not null,
  quote_time timestamptz,
  collected_at timestamptz not null default now(),
  primary key (tracked_id, eval_date, eval_slot)
);

create table if not exists dashboard_cache_latest (
  cache_key text primary key,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);

create index if not exists idx_kiwoom_intraday_trade_date on kiwoom_intraday_features_latest(trade_date desc, market, ticker);
create index if not exists idx_kiwoom_condition_hits_trade_date on kiwoom_condition_hits(trade_date desc, ticker);
create index if not exists idx_kiwoom_positions_account on kiwoom_account_positions_latest(account_no, updated_at desc);
create index if not exists idx_kiwoom_orders_account on kiwoom_order_execution_events(account_no, updated_at desc);

-- 종가배팅 조회 전용 read model view.
create or replace view vw_jongga_signal_read as
select
  jr.run_id,
  jr.run_date,
  jr.created_at as run_created_at,
  jr.runtime_meta,
  jr.total_candidates,
  jr.filtered_count,
  js.signal_rank,
  js.stock_code,
  js.stock_name,
  js.market,
  js.sector,
  js.signal_date,
  js.signal_time,
  js.grade,
  coalesce((js.score->>'total')::int, 0) as score_total,
  coalesce((js.score->>'news')::int, 0) as score_news,
  coalesce((js.score->>'supply')::int, 0) as score_supply,
  coalesce((js.score->>'chart')::int, 0) as score_chart,
  coalesce((js.score->>'volume')::int, 0) as score_volume,
  coalesce((js.score->>'candle')::int, 0) as score_candle,
  coalesce((js.score->>'consolidation')::int, 0) as score_consolidation,
  coalesce((js.score->>'market')::int, 0) as score_market,
  coalesce((js.score->>'program')::int, 0) as score_program,
  js.score,
  js.checklist,
  js.news_items,
  js.ai_overall,
  js.foreign_5d,
  js.inst_5d,
  js.individual_5d,
  js.current_price,
  js.entry_price,
  js.stop_price,
  js.target_price,
  js.r_value,
  js.position_size,
  js.quantity,
  js.r_multiplier,
  js.trading_value,
  js.change_pct,
  js.status,
  js.created_at as signal_created_at,
  coalesce(js.ai_overall->>'summary', '') as ai_summary,
  coalesce(js.ai_overall->>'status', '') as ai_status,
  coalesce(js.ai_overall->>'opinion', '') as ai_opinion,
  coalesce(js.ai_overall->'meta'->'evidence', '[]'::jsonb) as ai_evidence,
  coalesce(js.ai_overall->'meta'->'breakdown', '{}'::jsonb) as ai_breakdown,
  coalesce(js.ai_overall->'market_context', '{}'::jsonb) as market_context,
  coalesce(js.ai_overall->'program_context', '{}'::jsonb) as program_context,
  coalesce(js.ai_overall->>'base_grade', js.ai_overall->'meta'->'decision'->>'base_grade', js.grade) as base_grade,
  coalesce(js.ai_overall->'meta'->'decision'->>'status', '') as decision_status,
  coalesce(js.ai_overall->'external_market_context', jr.runtime_meta->'external_market_context', '{}'::jsonb) as external_market_context,
  coalesce(js.ai_overall->'market_policy', js.ai_overall->'meta'->'decision'->'grade_policy', '{}'::jsonb) as market_policy,
  coalesce((js.score->>'sector')::int, 0) as score_sector,
  coalesce((js.score->>'leader')::int, 0) as score_leader,
  coalesce((js.score->>'intraday')::int, 0) as score_intraday,
  coalesce((js.score->>'news_attention')::int, 0) as score_news_attention,
  coalesce(js.ai_overall->'sector_leadership', '{}'::jsonb) as sector_leadership,
  coalesce(js.ai_overall->'intraday_pressure', '{}'::jsonb) as intraday_pressure,
  coalesce(js.ai_overall->'news_attention', '{}'::jsonb) as news_attention,
  coalesce((js.score->>'stock_program')::int, 0) as score_stock_program,
  coalesce(js.ai_overall->'stock_program_context', '{}'::jsonb) as stock_program_context
from jongga_runs jr
join jongga_signals js on jr.run_id = js.run_id;

-- 배치 상태 화면 전용 view.
create or replace view vw_batch_status as
with table_stats as (
  select relname, coalesce(n_live_tup::bigint, 0) as approx_records
  from pg_stat_user_tables
  where schemaname = 'public'
),
latest_run as (
  select run_id, run_date, created_at, runtime_meta
  from jongga_runs
  order by created_at desc
  limit 1
),
latest_run_counts as (
  select lr.run_id, count(js.*)::bigint as signal_count
  from latest_run lr
  left join jongga_signals js on js.run_id = lr.run_id
  group by lr.run_id
)
select
  'daily_prices'::text as task_id,
  'Daily Prices'::text as title,
  'Closing Bet'::text as group_name,
  'db:public.naver_ohlcv_1d'::text as output_target,
  (select max(updated_at) from naver_ohlcv_1d) as updated_at,
  (select max(trade_date)::timestamptz from naver_ohlcv_1d) as max_data_time,
  coalesce((select approx_records from table_stats where relname = 'naver_ohlcv_1d'), 0) as records
union all
select
  'institutional_trend',
  'Institutional Trend',
  'Closing Bet',
  'db:public.naver_flows_1d',
  (select max(updated_at) from naver_flows_1d),
  (select max(trade_date)::timestamptz from naver_flows_1d),
  coalesce((select approx_records from table_stats where relname = 'naver_flows_1d'), 0)
union all
select
  'ai_analysis',
  'AI Analysis',
  'Closing Bet',
  'db:public.naver_news_items',
  (select max(updated_at) from naver_news_items),
  (select max(published_at) from naver_news_items),
  coalesce((select approx_records from table_stats where relname = 'naver_news_items'), 0)
union all
select
  'market_context',
  'Market Pulse',
  'Closing Bet',
  'db:public.naver_market_context_1d',
  (select max(updated_at) from naver_market_context_1d),
  (select max(trade_date)::timestamptz from naver_market_context_1d),
  coalesce((select approx_records from table_stats where relname = 'naver_market_context_1d'), 0)
union all
select
  'program_trend',
  'Program Trend',
  'Closing Bet',
  'db:public.naver_program_trend_1d',
  (select max(updated_at) from naver_program_trend_1d),
  (select max(trade_date)::timestamptz from naver_program_trend_1d),
  coalesce((select approx_records from table_stats where relname = 'naver_program_trend_1d'), 0)
union all
select
  'intraday_pressure',
  'Intraday Pressure',
  'Closing Bet',
  'db:public.kiwoom_intraday_feature_snapshots + public.kiwoom_program_snapshots',
  greatest(
    coalesce((select max(updated_at) from kiwoom_intraday_feature_snapshots), 'epoch'::timestamptz),
    coalesce((select max(updated_at) from kiwoom_program_snapshots), 'epoch'::timestamptz)
  ),
  greatest(
    coalesce((select max(snapshot_time) from kiwoom_intraday_feature_snapshots), 'epoch'::timestamptz),
    coalesce((select max(snapshot_time) from kiwoom_program_snapshots), 'epoch'::timestamptz)
  ),
  coalesce((select approx_records from table_stats where relname = 'kiwoom_intraday_feature_snapshots'), 0)
union all
select
  'vcp_signals',
  'VCP Signals',
  'Closing Bet',
  'db:public.naver_vcp_signals_latest',
  (select max(updated_at) from naver_vcp_signals_latest),
  (select max(trade_date)::timestamptz from naver_vcp_signals_latest),
  coalesce((select approx_records from table_stats where relname = 'naver_vcp_signals_latest'), 0)
union all
select
  'ai_jongga_v2',
  'AI Jongga V2',
  'Closing Bet',
  'db:public.jongga_runs + public.jongga_signals',
  (select created_at from latest_run),
  (select run_date::timestamptz from latest_run),
  coalesce((select signal_count from latest_run_counts), 0);

create extension if not exists pg_trgm;

create index if not exists idx_jongga_runs_date_created_new on jongga_runs(run_date desc, created_at desc);
create index if not exists idx_jongga_signals_runid_grade_rank_new on jongga_signals(run_id, grade, signal_rank asc);
create index if not exists idx_jongga_signals_runid_rank_new on jongga_signals(run_id, signal_rank asc);
create index if not exists idx_jongga_signals_runid_stock_new on jongga_signals(run_id, stock_code);
create index if not exists idx_jongga_signals_rundate_grade_rank_new on jongga_signals(run_date desc, grade, signal_rank asc);
create index if not exists idx_jongga_signals_stock_code_trgm_new on jongga_signals using gin (lower(stock_code) gin_trgm_ops);
create index if not exists idx_jongga_signals_stock_name_trgm_new on jongga_signals using gin (lower(stock_name) gin_trgm_ops);
create index if not exists idx_jongga_tracked_picks_run_date on jongga_tracked_picks(run_date desc, featured_rank asc);
create index if not exists idx_jongga_compare_prices_eval_date on jongga_compare_prices(eval_date desc, eval_slot);

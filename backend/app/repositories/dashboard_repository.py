from __future__ import annotations

import json
from typing import Any

from backend.app.core.database import db_connection


class DashboardRepository:
    def fetch_cached_dashboard(self, cache_key: str = 'main') -> dict[str, Any] | None:
        sql = """
        select payload, updated_at
        from dashboard_cache_latest
        where cache_key = %(cache_key)s
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'cache_key': cache_key})
                row = cur.fetchone()
        if not row:
            return None
        payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
        if payload and row.get('updated_at') and 'cached_updated_at' not in payload:
            payload = {**payload, 'cached_updated_at': row['updated_at'].isoformat()}
        return payload or None

    def save_cached_dashboard(self, payload: dict[str, Any], cache_key: str = 'main') -> None:
        sql = """
        insert into dashboard_cache_latest (cache_key, payload)
        values (%(cache_key)s, %(payload)s::jsonb)
        on conflict (cache_key) do update
        set payload = excluded.payload,
            updated_at = now()
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'cache_key': cache_key, 'payload': json.dumps(payload, ensure_ascii=False)})

    def fetch_market_rows(self) -> list[dict[str, Any]]:
        sql = """
        with latest_date as (
          select max(trade_date) as d from naver_market_context_1d
        )
        select trade_date, market, market_label, market_status, index_value, change_pct,
               rise_count, steady_count, fall_count, upper_count, lower_count, snapshot_time
        from naver_market_context_1d
        where trade_date = (select d from latest_date)
        order by market
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return list(cur.fetchall())

    def fetch_program_rows(self) -> list[dict[str, Any]]:
        sql = """
        with latest_date as (
          select max(trade_date) as d from naver_program_trend_1d
        )
        select trade_date, market, market_status, total_buy, total_sell, total_net, non_arbitrage_net, snapshot_time
        from naver_program_trend_1d
        where trade_date = (select d from latest_date)
        order by market
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return list(cur.fetchall())

    def fetch_latest_candidates(self, limit: int = 40) -> list[dict[str, Any]]:
        sql = """
        with latest_run as (
          select run_id
          from jongga_runs
          order by created_at desc
          limit 1
        ),
        latest_intraday as (
          select max(trade_date) as d from kiwoom_intraday_features_latest
        )
        select
          v.run_date,
          v.signal_rank,
          v.stock_code,
          v.stock_name,
          v.market,
          v.sector,
          v.grade,
          v.base_grade,
          v.score_sector,
          v.score_leader,
          v.score_intraday,
          v.score_news_attention,
          v.score_total,
          v.trading_value,
          v.change_pct,
          v.current_price,
          v.entry_price,
          v.stop_price,
          v.target_price,
          coalesce(flow.foreign_net_buy, 0) as foreign_1d,
          coalesce(flow.inst_net_buy, 0) as inst_1d,
          v.foreign_5d,
          v.inst_5d,
          v.ai_summary,
          v.ai_opinion,
          v.decision_status,
          v.sector_leadership,
          v.intraday_pressure,
          v.news_attention,
          v.market_policy,
          v.ai_evidence,
          v.news_items,
          coalesce(k.venue, '') as venue,
          coalesce(k.orderbook_imbalance, 0) as orderbook_imbalance,
          coalesce(k.execution_strength, 0) as execution_strength,
          coalesce(k.minute_pattern, '') as minute_pattern,
          coalesce(k.minute_breakout_score, 0) as minute_breakout_score,
          coalesce(k.volume_surge_ratio, 0) as volume_surge_ratio,
          coalesce(k.orderbook_surge_ratio, 0) as orderbook_surge_ratio,
          coalesce(k.vi_active, false) as vi_active,
          coalesce(k.vi_type, '') as vi_type,
          coalesce(k.condition_hit_count, 0) as condition_hit_count,
          coalesce(k.condition_names, '[]'::jsonb) as condition_names,
          coalesce(k.acc_trade_value, 0) as acc_trade_value,
          coalesce(k.acc_trade_volume, 0) as acc_trade_volume
        from vw_jongga_signal_read v
        join latest_run lr on lr.run_id = v.run_id
        left join naver_flows_1d flow
          on flow.trade_date = v.run_date
         and flow.ticker = v.stock_code
        left join kiwoom_intraday_features_latest k
          on k.trade_date = (select d from latest_intraday)
         and k.ticker = v.stock_code
        order by
          v.score_total desc,
          v.signal_rank asc,
          v.trading_value desc
        limit %(limit)s
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"limit": int(limit)})
                return list(cur.fetchall())

    def fetch_account_snapshot(self) -> dict[str, Any] | None:
        sql = """
        select account_no, snapshot_time, venue, total_purchase_amt, total_eval_amt,
               total_eval_profit, total_profit_rate, estimated_assets, holdings_count,
               realized_profit, unfilled_count, total_unfilled_qty, avg_fill_latency_ms,
               est_slippage_bps
        from kiwoom_account_snapshot_latest
        order by updated_at desc
        limit 1
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return cur.fetchone()

    def fetch_account_positions(self, account_no: str | None = None) -> list[dict[str, Any]]:
        sql = """
        with target_account as (
          select coalesce(
            nullif(%(account_no)s, ''),
            (
              select account_no
              from kiwoom_account_snapshot_latest
              order by updated_at desc
              limit 1
            )
          ) as account_no
        )
        select
          p.account_no,
          p.ticker,
          p.stock_name,
          p.quantity,
          p.available_qty,
          p.avg_price,
          p.current_price,
          p.eval_amount,
          p.profit_amount,
          p.profit_rate
        from kiwoom_account_positions_latest p
        join target_account t on t.account_no = p.account_no
        order by p.eval_amount desc, p.ticker asc
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'account_no': str(account_no or '').strip()})
                return list(cur.fetchall())

    def save_account_snapshot(self, payload: dict[str, Any]) -> None:
        sql = """
        insert into kiwoom_account_snapshot_latest (
          account_no, snapshot_time, venue, total_purchase_amt, total_eval_amt,
          total_eval_profit, total_profit_rate, estimated_assets, holdings_count,
          realized_profit, unfilled_count, total_unfilled_qty, avg_fill_latency_ms,
          est_slippage_bps, raw_payload
        ) values (
          %(account_no)s, %(snapshot_time)s, %(venue)s, %(total_purchase_amt)s, %(total_eval_amt)s,
          %(total_eval_profit)s, %(total_profit_rate)s, %(estimated_assets)s, %(holdings_count)s,
          %(realized_profit)s, %(unfilled_count)s, %(total_unfilled_qty)s, %(avg_fill_latency_ms)s,
          %(est_slippage_bps)s, %(raw_payload)s::jsonb
        )
        on conflict (account_no) do update
        set snapshot_time = excluded.snapshot_time,
            venue = excluded.venue,
            total_purchase_amt = excluded.total_purchase_amt,
            total_eval_amt = excluded.total_eval_amt,
            total_eval_profit = excluded.total_eval_profit,
            total_profit_rate = excluded.total_profit_rate,
            estimated_assets = excluded.estimated_assets,
            holdings_count = excluded.holdings_count,
            realized_profit = excluded.realized_profit,
            unfilled_count = excluded.unfilled_count,
            total_unfilled_qty = excluded.total_unfilled_qty,
            avg_fill_latency_ms = excluded.avg_fill_latency_ms,
            est_slippage_bps = excluded.est_slippage_bps,
            raw_payload = excluded.raw_payload,
            updated_at = now()
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {**payload, 'raw_payload': json.dumps(payload.get('raw_payload', {}), ensure_ascii=False)})

    def replace_account_positions(self, account_no: str, positions: list[dict[str, Any]]) -> int:
        account = str(account_no or '').strip()
        if not account:
            return 0
        delete_sql = "delete from kiwoom_account_positions_latest where account_no = %(account_no)s"
        insert_sql = """
        insert into kiwoom_account_positions_latest (
          account_no, ticker, stock_name, quantity, available_qty, avg_price,
          current_price, eval_amount, profit_amount, profit_rate
        ) values (
          %(account_no)s, %(ticker)s, %(stock_name)s, %(quantity)s, %(available_qty)s, %(avg_price)s,
          %(current_price)s, %(eval_amount)s, %(profit_amount)s, %(profit_rate)s
        )
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_sql, {'account_no': account})
                for position in positions:
                    cur.execute(insert_sql, {**position, 'account_no': account})
        return len(positions)

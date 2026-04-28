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
          case
            when coalesce(
              v.score->>'material_news_count',
              v.ai_overall->>'material_news_count',
              v.ai_overall->'meta'->'decision'->>'material_news_count',
              ''
            ) ~ '^-?[0-9]+$'
              then coalesce(
                v.score->>'material_news_count',
                v.ai_overall->>'material_news_count',
                v.ai_overall->'meta'->'decision'->>'material_news_count'
              )::int
            else 0
          end as material_news_count,
          coalesce(
            v.score->'llm_meta'->>'tone',
            v.ai_overall->>'news_tone',
            v.ai_overall->'meta'->'decision'->>'news_tone',
            ''
          ) as news_tone,
          case
            when lower(coalesce(
              v.score->'llm_meta'->>'tone',
              v.ai_overall->>'news_tone',
              v.ai_overall->'meta'->'decision'->>'news_tone',
              ''
            )) = 'negative' then 1
            when coalesce(
              v.ai_overall->>'negative_news_count',
              v.ai_overall->'meta'->'decision'->>'negative_news_count',
              ''
            ) ~ '^-?[0-9]+$'
              then coalesce(
                v.ai_overall->>'negative_news_count',
                v.ai_overall->'meta'->'decision'->>'negative_news_count'
              )::int
            else 0
          end as negative_news_count,
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

    def fetch_latest_tracked_pick_codes(self) -> list[str]:
        sql = """
        with latest_run as (
          select run_id
          from jongga_runs
          order by created_at desc
          limit 1
        )
        select tp.stock_code
        from jongga_tracked_picks tp
        join latest_run lr on lr.run_id = tp.run_id
        order by tp.featured_rank asc, tp.signal_rank asc
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [str(row.get("stock_code", "") or "").zfill(6) for row in cur.fetchall()]

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
        merged: dict[str, dict[str, Any]] = {}
        for position in positions:
            ticker = str(position.get('ticker', '') or '').strip().upper()
            if not ticker:
                continue
            quantity = int(position.get('quantity', 0) or 0)
            available_qty = int(position.get('available_qty', 0) or 0)
            avg_price = float(position.get('avg_price', 0) or 0)
            current_price = float(position.get('current_price', 0) or 0)
            eval_amount = int(position.get('eval_amount', 0) or 0)
            profit_amount = int(position.get('profit_amount', 0) or 0)
            profit_rate = float(position.get('profit_rate', 0) or 0)
            stock_name = str(position.get('stock_name', '') or '')
            if ticker not in merged:
                merged[ticker] = {
                    'ticker': ticker,
                    'stock_name': stock_name,
                    'quantity': quantity,
                    'available_qty': available_qty,
                    'avg_price': avg_price,
                    'current_price': current_price,
                    'eval_amount': eval_amount,
                    'profit_amount': profit_amount,
                    'profit_rate': profit_rate,
                    '_purchase_amount': avg_price * quantity,
                }
                continue
            current = merged[ticker]
            current['quantity'] += quantity
            current['available_qty'] += available_qty
            current['eval_amount'] += eval_amount
            current['profit_amount'] += profit_amount
            current['_purchase_amount'] += avg_price * quantity
            current['current_price'] = current_price or current['current_price']
            if not current['stock_name'] and stock_name:
                current['stock_name'] = stock_name
        normalized_positions: list[dict[str, Any]] = []
        for value in merged.values():
            qty = int(value.get('quantity', 0) or 0)
            purchase_amount = float(value.get('_purchase_amount', 0) or 0)
            avg_price = purchase_amount / qty if qty > 0 else float(value.get('avg_price', 0) or 0)
            profit_amount = int(value.get('profit_amount', 0) or 0)
            profit_rate = round((profit_amount / purchase_amount) * 100.0, 2) if purchase_amount > 0 else float(value.get('profit_rate', 0) or 0)
            normalized_positions.append(
                {
                    'ticker': value['ticker'],
                    'stock_name': value['stock_name'],
                    'quantity': qty,
                    'available_qty': int(value.get('available_qty', 0) or 0),
                    'avg_price': avg_price,
                    'current_price': float(value.get('current_price', 0) or 0),
                    'eval_amount': int(value.get('eval_amount', 0) or 0),
                    'profit_amount': profit_amount,
                    'profit_rate': profit_rate,
                }
            )
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
                for position in normalized_positions:
                    cur.execute(insert_sql, {**position, 'account_no': account})
        return len(normalized_positions)

    def upsert_order_execution_events(self, events: list[dict[str, Any]]) -> int:
        rows: list[dict[str, Any]] = []
        for event in events:
            account_no = str(event.get('account_no', '') or '').strip()
            order_no = str(event.get('order_no', '') or '').strip()
            if not account_no or not order_no:
                continue
            rows.append(
                {
                    'account_no': account_no,
                    'order_no': order_no,
                    'ticker': str(event.get('ticker', '') or '').strip().upper(),
                    'stock_name': str(event.get('stock_name', '') or ''),
                    'order_type': str(event.get('order_type', '') or ''),
                    'order_status': str(event.get('order_status', '') or ''),
                    'order_qty': int(event.get('order_qty', 0) or 0),
                    'filled_qty': int(event.get('filled_qty', 0) or 0),
                    'unfilled_qty': int(event.get('unfilled_qty', 0) or 0),
                    'order_price': float(event.get('order_price', 0) or 0),
                    'filled_price': float(event.get('filled_price', 0) or 0),
                    'order_time': event.get('order_time'),
                    'filled_time': event.get('filled_time'),
                    'fill_latency_ms': float(event.get('fill_latency_ms', 0) or 0),
                    'slippage_bps': float(event.get('slippage_bps', 0) or 0),
                    'venue': str(event.get('venue', '') or ''),
                    'raw_payload': json.dumps(event.get('raw_payload', {}) if isinstance(event.get('raw_payload'), dict) else {}, ensure_ascii=False),
                }
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_order_execution_events (
          account_no, order_no, ticker, stock_name, order_type, order_status,
          order_qty, filled_qty, unfilled_qty, order_price, filled_price, order_time,
          filled_time, fill_latency_ms, slippage_bps, venue, raw_payload
        ) values (
          %(account_no)s, %(order_no)s, %(ticker)s, %(stock_name)s, %(order_type)s, %(order_status)s,
          %(order_qty)s, %(filled_qty)s, %(unfilled_qty)s, %(order_price)s, %(filled_price)s, %(order_time)s,
          %(filled_time)s, %(fill_latency_ms)s, %(slippage_bps)s, %(venue)s, %(raw_payload)s::jsonb
        )
        on conflict (account_no, order_no) do update
        set ticker = excluded.ticker,
            stock_name = excluded.stock_name,
            order_type = excluded.order_type,
            order_status = excluded.order_status,
            order_qty = excluded.order_qty,
            filled_qty = excluded.filled_qty,
            unfilled_qty = excluded.unfilled_qty,
            order_price = excluded.order_price,
            filled_price = excluded.filled_price,
            order_time = excluded.order_time,
            filled_time = excluded.filled_time,
            fill_latency_ms = excluded.fill_latency_ms,
            slippage_bps = excluded.slippage_bps,
            venue = excluded.venue,
            raw_payload = excluded.raw_payload,
            updated_at = now()
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(sql, row)
        return len(rows)

    def fetch_order_execution_events(
        self,
        *,
        account_no: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
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
          e.account_no,
          e.order_no,
          e.ticker,
          e.stock_name,
          e.order_type,
          e.order_status,
          e.order_qty,
          e.filled_qty,
          e.unfilled_qty,
          e.order_price,
          e.filled_price,
          e.order_time,
          e.filled_time,
          e.fill_latency_ms,
          e.slippage_bps,
          e.venue,
          e.raw_payload,
          e.updated_at
        from kiwoom_order_execution_events e
        join target_account t on t.account_no = e.account_no
        where (
          %(date_from)s::date is null
          or coalesce(e.filled_time::date, e.order_time::date, e.updated_at::date) >= %(date_from)s::date
        )
          and (
            %(date_to)s::date is null
            or coalesce(e.filled_time::date, e.order_time::date, e.updated_at::date) <= %(date_to)s::date
          )
        order by coalesce(e.filled_time, e.order_time, e.updated_at) desc, e.order_no desc
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        'account_no': str(account_no or '').strip(),
                        'date_from': date_from,
                        'date_to': date_to,
                    },
                )
                return list(cur.fetchall())

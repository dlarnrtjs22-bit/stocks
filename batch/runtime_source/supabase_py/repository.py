from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from psycopg.rows import dict_row

from supabase_py.db import get_conn
from supabase_py.schema import ensure_schema


def _to_date(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v, errors="coerce").date()
    except Exception:
        return None


def _to_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None


def _to_int_num(v: Any) -> int:
    try:
        return int(float(v or 0))
    except Exception:
        return 0


def _to_float_num(v: Any) -> float:
    try:
        return float(v or 0)
    except Exception:
        return 0.0


class SupabaseRepository:
    def __init__(self, *, ensure_schema_on_init: bool = False) -> None:
        if ensure_schema_on_init:
            ensure_schema()

    @classmethod
    def from_env(cls, *, ensure_schema_on_init: bool = False) -> "SupabaseRepository":
        return cls(ensure_schema_on_init=ensure_schema_on_init)

    def _fetch_rows(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        with get_conn(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]

    def _fetch_one(self, sql: str, params: Tuple[Any, ...] = ()) -> Optional[Dict[str, Any]]:
        rows = self._fetch_rows(sql, params)
        return rows[0] if rows else None

    def _rows_to_df(self, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def delete_trade_dates(
        self,
        table_name: str,
        trade_dates: Iterable[date],
        tickers: Optional[Iterable[str]] = None,
    ) -> int:
        dates = [d for d in trade_dates if isinstance(d, date)]
        if not dates:
            return 0

        sql = f"delete from {table_name} where trade_date = any(%s)"
        params: List[Any] = [dates]
        if tickers:
            ticker_vals = sorted({str(t).zfill(6) for t in tickers if str(t).strip()})
            if ticker_vals:
                sql += " and ticker = any(%s)"
                params.append(ticker_vals)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("set local statement_timeout = 0")
                cur.execute(sql, tuple(params))
                return int(cur.rowcount or 0)

    def delete_news_dates(
        self,
        published_dates: Iterable[date],
        tickers: Optional[Iterable[str]] = None,
    ) -> int:
        dates = [d for d in published_dates if isinstance(d, date)]
        if not dates:
            return 0

        sql = "delete from naver_news_items where published_at::date = any(%s)"
        params: List[Any] = [dates]
        if tickers:
            ticker_vals = sorted({str(t).zfill(6) for t in tickers if str(t).strip()})
            if ticker_vals:
                sql += " and ticker = any(%s)"
                params.append(ticker_vals)

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("set local statement_timeout = 0")
                cur.execute(sql, tuple(params))
                return int(cur.rowcount or 0)

    def upsert_universe(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        records = []
        for _, r in df.iterrows():
            ticker = str(r.get("ticker", "")).zfill(6)
            if not ticker:
                continue
            records.append(
                (
                    ticker,
                    str(r.get("name", "")),
                    str(r.get("market", "")),
                    int(float(r.get("market_cap_eok", 0) or 0)),
                    int(float(r.get("raw_volume", 0) or 0)),
                )
            )

        if not records:
            return 0

        sql = """
        insert into naver_universe (ticker, name, market, market_cap_eok, raw_volume)
        values (%s, %s, %s, %s, %s)
        on conflict (ticker) do update
        set name=excluded.name,
            market=excluded.market,
            market_cap_eok=excluded.market_cap_eok,
            raw_volume=excluded.raw_volume,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, records)
        return len(records)

    def upsert_ohlcv(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "date",
            "ticker",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trading_value",
            "foreign_retention_rate",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for d_raw, ticker_raw, open_v, high_v, low_v, close_v, volume_v, trading_value_v, foreign_rate_v in frame[required].itertuples(index=False, name=None):
            d = _to_date(d_raw)
            ticker = str(ticker_raw or "").zfill(6)
            if d is None or not ticker:
                continue
            rows.append(
                (
                    d,
                    ticker,
                    float(open_v or 0),
                    float(high_v or 0),
                    float(low_v or 0),
                    float(close_v or 0),
                    int(float(volume_v or 0)),
                    int(float(trading_value_v or 0)),
                    float(foreign_rate_v or 0),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into naver_ohlcv_1d (
          trade_date, ticker, open_price, high_price, low_price, close_price,
          volume, trading_value, foreign_retention_rate
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, ticker) do update
        set open_price=excluded.open_price,
            high_price=excluded.high_price,
            low_price=excluded.low_price,
            close_price=excluded.close_price,
            volume=excluded.volume,
            trading_value=excluded.trading_value,
            foreign_retention_rate=excluded.foreign_retention_rate,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_flows(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = ["date", "ticker", "foreign_net_buy", "inst_net_buy", "retail_net_buy"]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for d_raw, ticker_raw, foreign_v, inst_v, retail_v in frame[required].itertuples(index=False, name=None):
            d = _to_date(d_raw)
            ticker = str(ticker_raw or "").zfill(6)
            if d is None or not ticker:
                continue
            rows.append(
                (
                    d,
                    ticker,
                    int(float(foreign_v or 0)),
                    int(float(inst_v or 0)),
                    int(float(retail_v or 0)),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into naver_flows_1d (trade_date, ticker, foreign_net_buy, inst_net_buy, retail_net_buy)
        values (%s,%s,%s,%s,%s)
        on conflict (trade_date, ticker) do update
        set foreign_net_buy=excluded.foreign_net_buy,
            inst_net_buy=excluded.inst_net_buy,
            retail_net_buy=excluded.retail_net_buy,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_news(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "ticker",
            "name",
            "published_at",
            "title",
            "summary",
            "source",
            "url",
            "relevance_score",
            "is_fallback",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for ticker_raw, name_raw, published_raw, title_raw, summary_raw, source_raw, url_raw, relevance_raw, fallback_raw in frame[required].itertuples(index=False, name=None):
            ticker = str(ticker_raw or "").zfill(6)
            title = str(title_raw or "").strip()
            if not ticker or not title:
                continue
            rows.append(
                (
                    ticker,
                    str(name_raw or ""),
                    _to_dt(published_raw),
                    title,
                    str(summary_raw or ""),
                    str(source_raw or ""),
                    str(url_raw or ""),
                    float(relevance_raw or 0),
                    bool(int(float(fallback_raw or 0))),
                )
            )

        if not rows:
            return 0

        sql = """
        insert into naver_news_items (
          ticker, name, published_at, title, summary, source, url, relevance_score, is_fallback
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (ticker, title, published_at, url) do update
        set name=excluded.name,
            summary=excluded.summary,
            source=excluded.source,
            relevance_score=excluded.relevance_score,
            is_fallback=excluded.is_fallback,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_snapshot(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        for _, r in df.iterrows():
            d = _to_date(r.get("date"))
            ticker = str(r.get("ticker", "")).zfill(6)
            if d is None or not ticker:
                continue
            rows.append(
                (
                    d,
                    ticker,
                    str(r.get("name", "")),
                    str(r.get("market", "")),
                    _to_float_num(r.get("close", 0)),
                    _to_float_num(r.get("change_pct", 0)),
                    _to_int_num(r.get("volume", 0)),
                    _to_int_num(r.get("trading_value", 0)),
                    _to_int_num(r.get("market_cap_eok", 0)),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into naver_latest_snapshot (
          trade_date, ticker, name, market, close_price, change_pct, volume, trading_value, market_cap_eok
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, ticker) do update
        set name=excluded.name,
            market=excluded.market,
            close_price=excluded.close_price,
            change_pct=excluded.change_pct,
            volume=excluded.volume,
            trading_value=excluded.trading_value,
            market_cap_eok=excluded.market_cap_eok,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_market_context(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "trade_date",
            "market",
            "market_label",
            "market_status",
            "index_value",
            "change_pct",
            "rise_count",
            "steady_count",
            "fall_count",
            "upper_count",
            "lower_count",
            "snapshot_time",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                trade_date_raw,
                market_raw,
                market_label_raw,
                market_status_raw,
                index_value_raw,
                change_pct_raw,
                rise_count_raw,
                steady_count_raw,
                fall_count_raw,
                upper_count_raw,
                lower_count_raw,
                snapshot_time_raw,
            ) = values
            trade_date = _to_date(trade_date_raw)
            market = str(market_raw or "").strip().upper()
            if trade_date is None or not market:
                continue
            rows.append(
                (
                    trade_date,
                    market,
                    str(market_label_raw or market),
                    str(market_status_raw or ""),
                    float(index_value_raw or 0),
                    float(change_pct_raw or 0),
                    int(float(rise_count_raw or 0)),
                    int(float(steady_count_raw or 0)),
                    int(float(fall_count_raw or 0)),
                    int(float(upper_count_raw or 0)),
                    int(float(lower_count_raw or 0)),
                    _to_dt(snapshot_time_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into naver_market_context_1d (
          trade_date, market, market_label, market_status, index_value, change_pct,
          rise_count, steady_count, fall_count, upper_count, lower_count, snapshot_time
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, market) do update
        set market_label=excluded.market_label,
            market_status=excluded.market_status,
            index_value=excluded.index_value,
            change_pct=excluded.change_pct,
            rise_count=excluded.rise_count,
            steady_count=excluded.steady_count,
            fall_count=excluded.fall_count,
            upper_count=excluded.upper_count,
            lower_count=excluded.lower_count,
            snapshot_time=excluded.snapshot_time,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_program_trend(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "trade_date",
            "market",
            "market_status",
            "arbitrage_buy",
            "arbitrage_sell",
            "arbitrage_net",
            "non_arbitrage_buy",
            "non_arbitrage_sell",
            "non_arbitrage_net",
            "total_buy",
            "total_sell",
            "total_net",
            "snapshot_time",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                trade_date_raw,
                market_raw,
                market_status_raw,
                arbitrage_buy_raw,
                arbitrage_sell_raw,
                arbitrage_net_raw,
                non_arbitrage_buy_raw,
                non_arbitrage_sell_raw,
                non_arbitrage_net_raw,
                total_buy_raw,
                total_sell_raw,
                total_net_raw,
                snapshot_time_raw,
            ) = values
            trade_date = _to_date(trade_date_raw)
            market = str(market_raw or "").strip().upper()
            if trade_date is None or not market:
                continue
            rows.append(
                (
                    trade_date,
                    market,
                    str(market_status_raw or ""),
                    int(float(arbitrage_buy_raw or 0)),
                    int(float(arbitrage_sell_raw or 0)),
                    int(float(arbitrage_net_raw or 0)),
                    int(float(non_arbitrage_buy_raw or 0)),
                    int(float(non_arbitrage_sell_raw or 0)),
                    int(float(non_arbitrage_net_raw or 0)),
                    int(float(total_buy_raw or 0)),
                    int(float(total_sell_raw or 0)),
                    int(float(total_net_raw or 0)),
                    _to_dt(snapshot_time_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into naver_program_trend_1d (
          trade_date, market, market_status, arbitrage_buy, arbitrage_sell, arbitrage_net,
          non_arbitrage_buy, non_arbitrage_sell, non_arbitrage_net, total_buy, total_sell,
          total_net, snapshot_time
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, market) do update
        set market_status=excluded.market_status,
            arbitrage_buy=excluded.arbitrage_buy,
            arbitrage_sell=excluded.arbitrage_sell,
            arbitrage_net=excluded.arbitrage_net,
            non_arbitrage_buy=excluded.non_arbitrage_buy,
            non_arbitrage_sell=excluded.non_arbitrage_sell,
            non_arbitrage_net=excluded.non_arbitrage_net,
            total_buy=excluded.total_buy,
            total_sell=excluded.total_sell,
            total_net=excluded.total_net,
            snapshot_time=excluded.snapshot_time,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_vcp_signals(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        seen_keys = set()
        for _, r in df.iterrows():
            d = _to_date(r.get("date"))
            ticker = str(r.get("ticker", "")).zfill(6)
            if d is None or not ticker:
                continue
            key = (d, ticker)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append(
                (
                    d,
                    ticker,
                    str(r.get("signal", "")),
                    float(r.get("vcp_score", 0) or 0),
                    float(r.get("close", 0) or 0),
                    int(float(r.get("volume", 0) or 0)),
                    float(r.get("ma20", 0) or 0),
                    float(r.get("vol_ratio", 0) or 0),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into naver_vcp_signals_latest (
          trade_date, ticker, signal, vcp_score, close_price, volume, ma20, vol_ratio
        ) values (%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, ticker) do update
        set signal=excluded.signal,
            vcp_score=excluded.vcp_score,
            close_price=excluded.close_price,
            volume=excluded.volume,
            ma20=excluded.ma20,
            vol_ratio=excluded.vol_ratio,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("set local statement_timeout = 0")
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_kiwoom_intraday_features(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "trade_date",
            "ticker",
            "stock_name",
            "market",
            "venue",
            "current_price",
            "change_pct",
            "bid_total",
            "ask_total",
            "orderbook_imbalance",
            "execution_strength",
            "tick_volume",
            "minute_pattern",
            "minute_breakout_score",
            "volume_surge_ratio",
            "orderbook_surge_ratio",
            "vi_active",
            "vi_type",
            "condition_hit_count",
            "condition_names",
            "acc_trade_value",
            "acc_trade_volume",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                trade_date_raw,
                ticker_raw,
                stock_name_raw,
                market_raw,
                venue_raw,
                current_price_raw,
                change_pct_raw,
                bid_total_raw,
                ask_total_raw,
                orderbook_imbalance_raw,
                execution_strength_raw,
                tick_volume_raw,
                minute_pattern_raw,
                minute_breakout_score_raw,
                volume_surge_ratio_raw,
                orderbook_surge_ratio_raw,
                vi_active_raw,
                vi_type_raw,
                condition_hit_count_raw,
                condition_names_raw,
                acc_trade_value_raw,
                acc_trade_volume_raw,
            ) = values
            trade_date = _to_date(trade_date_raw)
            ticker = str(ticker_raw or "").strip().upper()
            if trade_date is None or not ticker:
                continue
            condition_names = condition_names_raw if isinstance(condition_names_raw, list) else []
            rows.append(
                (
                    trade_date,
                    ticker,
                    str(stock_name_raw or ""),
                    str(market_raw or ""),
                    str(venue_raw or ""),
                    _to_float_num(current_price_raw),
                    _to_float_num(change_pct_raw),
                    _to_int_num(bid_total_raw),
                    _to_int_num(ask_total_raw),
                    _to_float_num(orderbook_imbalance_raw),
                    _to_float_num(execution_strength_raw),
                    _to_int_num(tick_volume_raw),
                    str(minute_pattern_raw or ""),
                    _to_float_num(minute_breakout_score_raw),
                    _to_float_num(volume_surge_ratio_raw),
                    _to_float_num(orderbook_surge_ratio_raw),
                    bool(vi_active_raw),
                    str(vi_type_raw or ""),
                    _to_int_num(condition_hit_count_raw),
                    json.dumps(condition_names, ensure_ascii=False),
                    _to_int_num(acc_trade_value_raw),
                    _to_int_num(acc_trade_volume_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_intraday_features_latest (
          trade_date, ticker, stock_name, market, venue, current_price, change_pct,
          bid_total, ask_total, orderbook_imbalance, execution_strength, tick_volume,
          minute_pattern, minute_breakout_score, volume_surge_ratio, orderbook_surge_ratio,
          vi_active, vi_type, condition_hit_count, condition_names, acc_trade_value, acc_trade_volume
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
        on conflict (trade_date, ticker) do update
        set stock_name=excluded.stock_name,
            market=excluded.market,
            venue=excluded.venue,
            current_price=excluded.current_price,
            change_pct=excluded.change_pct,
            bid_total=excluded.bid_total,
            ask_total=excluded.ask_total,
            orderbook_imbalance=excluded.orderbook_imbalance,
            execution_strength=excluded.execution_strength,
            tick_volume=excluded.tick_volume,
            minute_pattern=excluded.minute_pattern,
            minute_breakout_score=excluded.minute_breakout_score,
            volume_surge_ratio=excluded.volume_surge_ratio,
            orderbook_surge_ratio=excluded.orderbook_surge_ratio,
            vi_active=excluded.vi_active,
            vi_type=excluded.vi_type,
            condition_hit_count=excluded.condition_hit_count,
            condition_names=excluded.condition_names,
            acc_trade_value=excluded.acc_trade_value,
            acc_trade_volume=excluded.acc_trade_volume,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_kiwoom_intraday_snapshots(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "trade_date",
            "snapshot_time",
            "ticker",
            "stock_name",
            "market",
            "venue",
            "current_price",
            "change_pct",
            "bid_total",
            "ask_total",
            "orderbook_imbalance",
            "execution_strength",
            "tick_volume",
            "minute_pattern",
            "minute_breakout_score",
            "volume_surge_ratio",
            "orderbook_surge_ratio",
            "vi_active",
            "vi_type",
            "condition_hit_count",
            "condition_names",
            "acc_trade_value",
            "acc_trade_volume",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                trade_date_raw,
                snapshot_time_raw,
                ticker_raw,
                stock_name_raw,
                market_raw,
                venue_raw,
                current_price_raw,
                change_pct_raw,
                bid_total_raw,
                ask_total_raw,
                orderbook_imbalance_raw,
                execution_strength_raw,
                tick_volume_raw,
                minute_pattern_raw,
                minute_breakout_score_raw,
                volume_surge_ratio_raw,
                orderbook_surge_ratio_raw,
                vi_active_raw,
                vi_type_raw,
                condition_hit_count_raw,
                condition_names_raw,
                acc_trade_value_raw,
                acc_trade_volume_raw,
            ) = values
            trade_date = _to_date(trade_date_raw)
            snapshot_time = _to_dt(snapshot_time_raw)
            ticker = str(ticker_raw or "").strip().upper()
            if trade_date is None or snapshot_time is None or not ticker:
                continue
            condition_names = condition_names_raw if isinstance(condition_names_raw, list) else []
            rows.append(
                (
                    trade_date,
                    snapshot_time,
                    ticker,
                    str(stock_name_raw or ""),
                    str(market_raw or ""),
                    str(venue_raw or ""),
                    _to_float_num(current_price_raw),
                    _to_float_num(change_pct_raw),
                    _to_int_num(bid_total_raw),
                    _to_int_num(ask_total_raw),
                    _to_float_num(orderbook_imbalance_raw),
                    _to_float_num(execution_strength_raw),
                    _to_int_num(tick_volume_raw),
                    str(minute_pattern_raw or ""),
                    _to_float_num(minute_breakout_score_raw),
                    _to_float_num(volume_surge_ratio_raw),
                    _to_float_num(orderbook_surge_ratio_raw),
                    bool(vi_active_raw),
                    str(vi_type_raw or ""),
                    _to_int_num(condition_hit_count_raw),
                    json.dumps(condition_names, ensure_ascii=False),
                    _to_int_num(acc_trade_value_raw),
                    _to_int_num(acc_trade_volume_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_intraday_feature_snapshots (
          trade_date, snapshot_time, ticker, stock_name, market, venue, current_price, change_pct,
          bid_total, ask_total, orderbook_imbalance, execution_strength, tick_volume,
          minute_pattern, minute_breakout_score, volume_surge_ratio, orderbook_surge_ratio,
          vi_active, vi_type, condition_hit_count, condition_names, acc_trade_value, acc_trade_volume
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
        on conflict (snapshot_time, ticker) do update
        set stock_name=excluded.stock_name,
            market=excluded.market,
            venue=excluded.venue,
            current_price=excluded.current_price,
            change_pct=excluded.change_pct,
            bid_total=excluded.bid_total,
            ask_total=excluded.ask_total,
            orderbook_imbalance=excluded.orderbook_imbalance,
            execution_strength=excluded.execution_strength,
            tick_volume=excluded.tick_volume,
            minute_pattern=excluded.minute_pattern,
            minute_breakout_score=excluded.minute_breakout_score,
            volume_surge_ratio=excluded.volume_surge_ratio,
            orderbook_surge_ratio=excluded.orderbook_surge_ratio,
            vi_active=excluded.vi_active,
            vi_type=excluded.vi_type,
            condition_hit_count=excluded.condition_hit_count,
            condition_names=excluded.condition_names,
            acc_trade_value=excluded.acc_trade_value,
            acc_trade_volume=excluded.acc_trade_volume,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_kiwoom_condition_hits(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = ["trade_date", "ticker", "condition_seq", "condition_name", "hit_count", "first_seen_at", "last_seen_at"]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for trade_date_raw, ticker_raw, condition_seq_raw, condition_name_raw, hit_count_raw, first_seen_at_raw, last_seen_at_raw in frame[required].itertuples(index=False, name=None):
            trade_date = _to_date(trade_date_raw)
            ticker = str(ticker_raw or "").strip().upper()
            condition_seq = str(condition_seq_raw or "").strip()
            if trade_date is None or not ticker or not condition_seq:
                continue
            rows.append(
                (
                    trade_date,
                    ticker,
                    condition_seq,
                    str(condition_name_raw or ""),
                    _to_int_num(hit_count_raw) or 1,
                    _to_dt(first_seen_at_raw),
                    _to_dt(last_seen_at_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_condition_hits (
          trade_date, ticker, condition_seq, condition_name, hit_count, first_seen_at, last_seen_at
        ) values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, ticker, condition_seq) do update
        set condition_name=excluded.condition_name,
            hit_count=excluded.hit_count,
            first_seen_at=coalesce(kiwoom_condition_hits.first_seen_at, excluded.first_seen_at),
            last_seen_at=excluded.last_seen_at,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_kiwoom_program_snapshots(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "trade_date",
            "snapshot_time",
            "market",
            "market_status",
            "arbitrage_buy",
            "arbitrage_sell",
            "arbitrage_net",
            "non_arbitrage_buy",
            "non_arbitrage_sell",
            "non_arbitrage_net",
            "total_buy",
            "total_sell",
            "total_net",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                trade_date_raw,
                snapshot_time_raw,
                market_raw,
                market_status_raw,
                arbitrage_buy_raw,
                arbitrage_sell_raw,
                arbitrage_net_raw,
                non_arbitrage_buy_raw,
                non_arbitrage_sell_raw,
                non_arbitrage_net_raw,
                total_buy_raw,
                total_sell_raw,
                total_net_raw,
            ) = values
            trade_date = _to_date(trade_date_raw)
            snapshot_time = _to_dt(snapshot_time_raw)
            market = str(market_raw or "").strip().upper()
            if trade_date is None or snapshot_time is None or not market:
                continue
            rows.append(
                (
                    trade_date,
                    snapshot_time,
                    market,
                    str(market_status_raw or ""),
                    _to_int_num(arbitrage_buy_raw),
                    _to_int_num(arbitrage_sell_raw),
                    _to_int_num(arbitrage_net_raw),
                    _to_int_num(non_arbitrage_buy_raw),
                    _to_int_num(non_arbitrage_sell_raw),
                    _to_int_num(non_arbitrage_net_raw),
                    _to_int_num(total_buy_raw),
                    _to_int_num(total_sell_raw),
                    _to_int_num(total_net_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_program_snapshots (
          trade_date, snapshot_time, market, market_status,
          arbitrage_buy, arbitrage_sell, arbitrage_net,
          non_arbitrage_buy, non_arbitrage_sell, non_arbitrage_net,
          total_buy, total_sell, total_net
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (snapshot_time, market) do update
        set market_status=excluded.market_status,
            arbitrage_buy=excluded.arbitrage_buy,
            arbitrage_sell=excluded.arbitrage_sell,
            arbitrage_net=excluded.arbitrage_net,
            non_arbitrage_buy=excluded.non_arbitrage_buy,
            non_arbitrage_sell=excluded.non_arbitrage_sell,
            non_arbitrage_net=excluded.non_arbitrage_net,
            total_buy=excluded.total_buy,
            total_sell=excluded.total_sell,
            total_net=excluded.total_net,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_kiwoom_stock_program_latest(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "trade_date",
            "ticker",
            "stock_name",
            "market",
            "venue",
            "latest_time",
            "current_price",
            "change_pct",
            "program_sell_amt",
            "program_buy_amt",
            "program_net_buy_amt",
            "program_sell_qty",
            "program_buy_qty",
            "program_net_buy_qty",
            "delta_10m_amt",
            "delta_30m_amt",
            "delta_10m_qty",
            "delta_30m_qty",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                trade_date_raw,
                ticker_raw,
                stock_name_raw,
                market_raw,
                venue_raw,
                latest_time_raw,
                current_price_raw,
                change_pct_raw,
                program_sell_amt_raw,
                program_buy_amt_raw,
                program_net_buy_amt_raw,
                program_sell_qty_raw,
                program_buy_qty_raw,
                program_net_buy_qty_raw,
                delta_10m_amt_raw,
                delta_30m_amt_raw,
                delta_10m_qty_raw,
                delta_30m_qty_raw,
            ) = values
            trade_date = _to_date(trade_date_raw)
            ticker = str(ticker_raw or "").strip().upper()
            if trade_date is None or not ticker:
                continue
            rows.append(
                (
                    trade_date,
                    ticker,
                    str(stock_name_raw or ""),
                    str(market_raw or ""),
                    str(venue_raw or ""),
                    _to_dt(latest_time_raw),
                    _to_float_num(current_price_raw),
                    _to_float_num(change_pct_raw),
                    _to_int_num(program_sell_amt_raw),
                    _to_int_num(program_buy_amt_raw),
                    _to_int_num(program_net_buy_amt_raw),
                    _to_int_num(program_sell_qty_raw),
                    _to_int_num(program_buy_qty_raw),
                    _to_int_num(program_net_buy_qty_raw),
                    _to_int_num(delta_10m_amt_raw),
                    _to_int_num(delta_30m_amt_raw),
                    _to_int_num(delta_10m_qty_raw),
                    _to_int_num(delta_30m_qty_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_stock_program_trades_latest (
          trade_date, ticker, stock_name, market, venue, latest_time, current_price, change_pct,
          program_sell_amt, program_buy_amt, program_net_buy_amt,
          program_sell_qty, program_buy_qty, program_net_buy_qty,
          delta_10m_amt, delta_30m_amt, delta_10m_qty, delta_30m_qty
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, ticker) do update
        set stock_name=excluded.stock_name,
            market=excluded.market,
            venue=excluded.venue,
            latest_time=excluded.latest_time,
            current_price=excluded.current_price,
            change_pct=excluded.change_pct,
            program_sell_amt=excluded.program_sell_amt,
            program_buy_amt=excluded.program_buy_amt,
            program_net_buy_amt=excluded.program_net_buy_amt,
            program_sell_qty=excluded.program_sell_qty,
            program_buy_qty=excluded.program_buy_qty,
            program_net_buy_qty=excluded.program_net_buy_qty,
            delta_10m_amt=excluded.delta_10m_amt,
            delta_30m_amt=excluded.delta_30m_amt,
            delta_10m_qty=excluded.delta_10m_qty,
            delta_30m_qty=excluded.delta_30m_qty,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_kiwoom_stock_program_daily(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "trade_date",
            "ticker",
            "stock_name",
            "venue",
            "current_price",
            "change_pct",
            "trade_volume",
            "program_sell_amt",
            "program_buy_amt",
            "program_net_buy_amt",
            "program_sell_qty",
            "program_buy_qty",
            "program_net_buy_qty",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                trade_date_raw,
                ticker_raw,
                stock_name_raw,
                venue_raw,
                current_price_raw,
                change_pct_raw,
                trade_volume_raw,
                program_sell_amt_raw,
                program_buy_amt_raw,
                program_net_buy_amt_raw,
                program_sell_qty_raw,
                program_buy_qty_raw,
                program_net_buy_qty_raw,
            ) = values
            trade_date = _to_date(trade_date_raw)
            ticker = str(ticker_raw or "").strip().upper()
            if trade_date is None or not ticker:
                continue
            rows.append(
                (
                    trade_date,
                    ticker,
                    str(stock_name_raw or ""),
                    str(venue_raw or ""),
                    _to_float_num(current_price_raw),
                    _to_float_num(change_pct_raw),
                    _to_int_num(trade_volume_raw),
                    _to_int_num(program_sell_amt_raw),
                    _to_int_num(program_buy_amt_raw),
                    _to_int_num(program_net_buy_amt_raw),
                    _to_int_num(program_sell_qty_raw),
                    _to_int_num(program_buy_qty_raw),
                    _to_int_num(program_net_buy_qty_raw),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_stock_program_daily (
          trade_date, ticker, stock_name, venue, current_price, change_pct, trade_volume,
          program_sell_amt, program_buy_amt, program_net_buy_amt,
          program_sell_qty, program_buy_qty, program_net_buy_qty
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (trade_date, ticker) do update
        set stock_name=excluded.stock_name,
            venue=excluded.venue,
            current_price=excluded.current_price,
            change_pct=excluded.change_pct,
            trade_volume=excluded.trade_volume,
            program_sell_amt=excluded.program_sell_amt,
            program_buy_amt=excluded.program_buy_amt,
            program_net_buy_amt=excluded.program_net_buy_amt,
            program_sell_qty=excluded.program_sell_qty,
            program_buy_qty=excluded.program_buy_qty,
            program_net_buy_qty=excluded.program_net_buy_qty,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def upsert_kiwoom_account_snapshot(self, payload: Dict[str, Any]) -> int:
        account_no = str(payload.get("account_no", "")).strip()
        if not account_no:
            return 0
        sql = """
        insert into kiwoom_account_snapshot_latest (
          account_no, snapshot_time, venue, total_purchase_amt, total_eval_amt,
          total_eval_profit, total_profit_rate, estimated_assets, holdings_count,
          realized_profit, unfilled_count, total_unfilled_qty, avg_fill_latency_ms,
          est_slippage_bps, raw_payload
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        on conflict (account_no) do update
        set snapshot_time=excluded.snapshot_time,
            venue=excluded.venue,
            total_purchase_amt=excluded.total_purchase_amt,
            total_eval_amt=excluded.total_eval_amt,
            total_eval_profit=excluded.total_eval_profit,
            total_profit_rate=excluded.total_profit_rate,
            estimated_assets=excluded.estimated_assets,
            holdings_count=excluded.holdings_count,
            realized_profit=excluded.realized_profit,
            unfilled_count=excluded.unfilled_count,
            total_unfilled_qty=excluded.total_unfilled_qty,
            avg_fill_latency_ms=excluded.avg_fill_latency_ms,
            est_slippage_bps=excluded.est_slippage_bps,
            raw_payload=excluded.raw_payload,
            updated_at=now()
        """
        params = (
            account_no,
            _to_dt(payload.get("snapshot_time")),
            str(payload.get("venue", "")),
            _to_int_num(payload.get("total_purchase_amt")),
            _to_int_num(payload.get("total_eval_amt")),
            _to_int_num(payload.get("total_eval_profit")),
            _to_float_num(payload.get("total_profit_rate")),
            _to_int_num(payload.get("estimated_assets")),
            _to_int_num(payload.get("holdings_count")),
            _to_int_num(payload.get("realized_profit")),
            _to_int_num(payload.get("unfilled_count")),
            _to_int_num(payload.get("total_unfilled_qty")),
            _to_float_num(payload.get("avg_fill_latency_ms")),
            _to_float_num(payload.get("est_slippage_bps")),
            json.dumps(payload.get("raw_payload", {}), ensure_ascii=False),
        )
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
        return 1

    def replace_kiwoom_account_positions(self, account_no: str, df: pd.DataFrame) -> int:
        account = str(account_no or "").strip()
        if not account:
            return 0
        rows = []
        if df is not None and not df.empty:
            required = ["ticker", "stock_name", "quantity", "available_qty", "avg_price", "current_price", "eval_amount", "profit_amount", "profit_rate"]
            frame = df.copy()
            for c in required:
                if c not in frame.columns:
                    frame[c] = None
            for ticker_raw, stock_name_raw, quantity_raw, available_qty_raw, avg_price_raw, current_price_raw, eval_amount_raw, profit_amount_raw, profit_rate_raw in frame[required].itertuples(index=False, name=None):
                ticker = str(ticker_raw or "").strip().upper()
                if not ticker:
                    continue
                rows.append(
                    (
                        account,
                        ticker,
                        str(stock_name_raw or ""),
                        _to_int_num(quantity_raw),
                        _to_int_num(available_qty_raw),
                        _to_float_num(avg_price_raw),
                        _to_float_num(current_price_raw),
                        _to_int_num(eval_amount_raw),
                        _to_int_num(profit_amount_raw),
                        _to_float_num(profit_rate_raw),
                    )
                )
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from kiwoom_account_positions_latest where account_no=%s", (account,))
                if rows:
                    cur.executemany(
                        """
                        insert into kiwoom_account_positions_latest (
                          account_no, ticker, stock_name, quantity, available_qty, avg_price,
                          current_price, eval_amount, profit_amount, profit_rate
                        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        rows,
                    )
        return len(rows)

    def upsert_kiwoom_order_execution_events(self, df: pd.DataFrame) -> int:
        if df is None or df.empty:
            return 0
        rows = []
        required = [
            "account_no",
            "order_no",
            "ticker",
            "stock_name",
            "order_type",
            "order_status",
            "order_qty",
            "filled_qty",
            "unfilled_qty",
            "order_price",
            "filled_price",
            "order_time",
            "filled_time",
            "fill_latency_ms",
            "slippage_bps",
            "venue",
            "raw_payload",
        ]
        frame = df.copy()
        for c in required:
            if c not in frame.columns:
                frame[c] = None
        for values in frame[required].itertuples(index=False, name=None):
            (
                account_no_raw,
                order_no_raw,
                ticker_raw,
                stock_name_raw,
                order_type_raw,
                order_status_raw,
                order_qty_raw,
                filled_qty_raw,
                unfilled_qty_raw,
                order_price_raw,
                filled_price_raw,
                order_time_raw,
                filled_time_raw,
                fill_latency_ms_raw,
                slippage_bps_raw,
                venue_raw,
                raw_payload_raw,
            ) = values
            account_no = str(account_no_raw or "").strip()
            order_no = str(order_no_raw or "").strip()
            if not account_no or not order_no:
                continue
            rows.append(
                (
                    account_no,
                    order_no,
                    str(ticker_raw or "").strip().upper(),
                    str(stock_name_raw or ""),
                    str(order_type_raw or ""),
                    str(order_status_raw or ""),
                    _to_int_num(order_qty_raw),
                    _to_int_num(filled_qty_raw),
                    _to_int_num(unfilled_qty_raw),
                    _to_float_num(order_price_raw),
                    _to_float_num(filled_price_raw),
                    _to_dt(order_time_raw),
                    _to_dt(filled_time_raw),
                    _to_float_num(fill_latency_ms_raw),
                    _to_float_num(slippage_bps_raw),
                    str(venue_raw or ""),
                    json.dumps(raw_payload_raw if isinstance(raw_payload_raw, dict) else {}, ensure_ascii=False),
                )
            )
        if not rows:
            return 0

        sql = """
        insert into kiwoom_order_execution_events (
          account_no, order_no, ticker, stock_name, order_type, order_status,
          order_qty, filled_qty, unfilled_qty, order_price, filled_price, order_time,
          filled_time, fill_latency_ms, slippage_bps, venue, raw_payload
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        on conflict (account_no, order_no) do update
        set ticker=excluded.ticker,
            stock_name=excluded.stock_name,
            order_type=excluded.order_type,
            order_status=excluded.order_status,
            order_qty=excluded.order_qty,
            filled_qty=excluded.filled_qty,
            unfilled_qty=excluded.unfilled_qty,
            order_price=excluded.order_price,
            filled_price=excluded.filled_price,
            order_time=excluded.order_time,
            filled_time=excluded.filled_time,
            fill_latency_ms=excluded.fill_latency_ms,
            slippage_bps=excluded.slippage_bps,
            venue=excluded.venue,
            raw_payload=excluded.raw_payload,
            updated_at=now()
        """
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        return len(rows)

    def load_universe_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            select ticker, name, market, market_cap_eok, raw_volume
            from naver_universe
            order by market, market_cap_eok desc nulls last, ticker
            """
        )
        return self._rows_to_df(rows)

    def load_ohlcv_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            select trade_date as date, ticker, open_price as open, high_price as high,
                   low_price as low, close_price as close, volume, trading_value,
                   foreign_retention_rate
            from naver_ohlcv_1d
            order by ticker, trade_date
            """
        )
        return self._rows_to_df(rows)

    def load_flows_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            select trade_date as date, ticker, foreign_net_buy, inst_net_buy, retail_net_buy
            from naver_flows_1d
            order by ticker, trade_date
            """
        )
        return self._rows_to_df(rows)

    def load_snapshot_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from naver_latest_snapshot
            )
            select s.trade_date as date, s.ticker, s.name, s.market,
                   s.close_price as close, s.change_pct, s.volume,
                   s.trading_value, s.market_cap_eok
            from naver_latest_snapshot s
            join latest_date l on s.trade_date = l.d
            order by s.change_pct desc, s.trading_value desc
            """
        )
        return self._rows_to_df(rows)

    def load_news_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            select ticker, name, published_at, title, summary, source, url,
                   relevance_score, is_fallback
            from naver_news_items
            order by ticker, published_at desc nulls last, relevance_score desc
            """
        )
        return self._rows_to_df(rows)

    def load_market_context_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from naver_market_context_1d
            )
            select trade_date, market, market_label, market_status, index_value, change_pct,
                   rise_count, steady_count, fall_count, upper_count, lower_count, snapshot_time
            from naver_market_context_1d
            where trade_date = (select d from latest_date)
            order by market
            """
        )
        return self._rows_to_df(rows)

    def load_program_trend_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from naver_program_trend_1d
            )
            select trade_date, market, market_status, arbitrage_buy, arbitrage_sell, arbitrage_net,
                   non_arbitrage_buy, non_arbitrage_sell, non_arbitrage_net, total_buy, total_sell,
                   total_net, snapshot_time
            from naver_program_trend_1d
            where trade_date = (select d from latest_date)
            order by market
            """
        )
        return self._rows_to_df(rows)

    def load_vcp_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from naver_vcp_signals_latest
            )
            select trade_date as date, ticker, signal, vcp_score,
                   close_price as close, volume, ma20, vol_ratio
            from naver_vcp_signals_latest
            where trade_date = (select d from latest_date)
            order by vcp_score desc, volume desc
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_intraday_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from kiwoom_intraday_features_latest
            )
            select trade_date, ticker, stock_name, market, venue, current_price, change_pct,
                   bid_total, ask_total, orderbook_imbalance, execution_strength, tick_volume,
                   minute_pattern, minute_breakout_score, volume_surge_ratio, orderbook_surge_ratio,
                   vi_active, vi_type, condition_hit_count, condition_names, acc_trade_value, acc_trade_volume
            from kiwoom_intraday_features_latest
            where trade_date = (select d from latest_date)
            order by market, change_pct desc nulls last, ticker
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_intraday_snapshot_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from kiwoom_intraday_feature_snapshots
            )
            select trade_date, snapshot_time, ticker, stock_name, market, venue, current_price, change_pct,
                   bid_total, ask_total, orderbook_imbalance, execution_strength, tick_volume,
                   minute_pattern, minute_breakout_score, volume_surge_ratio, orderbook_surge_ratio,
                   vi_active, vi_type, condition_hit_count, condition_names, acc_trade_value, acc_trade_volume
            from kiwoom_intraday_feature_snapshots
            where trade_date = (select d from latest_date)
            order by snapshot_time, market, ticker
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_stock_program_latest_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from kiwoom_stock_program_trades_latest
            )
            select trade_date, ticker, stock_name, market, venue, latest_time, current_price, change_pct,
                   program_sell_amt, program_buy_amt, program_net_buy_amt,
                   program_sell_qty, program_buy_qty, program_net_buy_qty,
                   delta_10m_amt, delta_30m_amt, delta_10m_qty, delta_30m_qty
            from kiwoom_stock_program_trades_latest
            where trade_date = (select d from latest_date)
            order by latest_time desc nulls last, ticker
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_stock_program_daily_df(self, lookback_days: int = 10) -> pd.DataFrame:
        rows = self._fetch_rows(
            f"""
            with latest_date as (
              select max(trade_date) as d from kiwoom_stock_program_daily
            )
            select trade_date, ticker, stock_name, venue, current_price, change_pct, trade_volume,
                   program_sell_amt, program_buy_amt, program_net_buy_amt,
                   program_sell_qty, program_buy_qty, program_net_buy_qty
            from kiwoom_stock_program_daily
            where trade_date >= ((select d from latest_date) - interval '{int(lookback_days)} days')
            order by trade_date, ticker
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_condition_hits_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from kiwoom_condition_hits
            )
            select trade_date, ticker, condition_seq, condition_name, hit_count, first_seen_at, last_seen_at
            from kiwoom_condition_hits
            where trade_date = (select d from latest_date)
            order by ticker, condition_name
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_program_snapshot_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            with latest_date as (
              select max(trade_date) as d from kiwoom_program_snapshots
            )
            select trade_date, snapshot_time, market, market_status,
                   arbitrage_buy, arbitrage_sell, arbitrage_net,
                   non_arbitrage_buy, non_arbitrage_sell, non_arbitrage_net,
                   total_buy, total_sell, total_net
            from kiwoom_program_snapshots
            where trade_date = (select d from latest_date)
            order by snapshot_time, market
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_account_snapshot_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            select account_no, snapshot_time, venue, total_purchase_amt, total_eval_amt,
                   total_eval_profit, total_profit_rate, estimated_assets, holdings_count,
                   realized_profit, unfilled_count, total_unfilled_qty, avg_fill_latency_ms,
                   est_slippage_bps, raw_payload
            from kiwoom_account_snapshot_latest
            order by updated_at desc, account_no
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_account_positions_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            select account_no, ticker, stock_name, quantity, available_qty, avg_price,
                   current_price, eval_amount, profit_amount, profit_rate, updated_at
            from kiwoom_account_positions_latest
            order by account_no, profit_rate desc nulls last, ticker
            """
        )
        return self._rows_to_df(rows)

    def load_kiwoom_order_events_df(self) -> pd.DataFrame:
        rows = self._fetch_rows(
            """
            select account_no, order_no, ticker, stock_name, order_type, order_status, order_qty,
                   filled_qty, unfilled_qty, order_price, filled_price, order_time, filled_time,
                   fill_latency_ms, slippage_bps, venue, raw_payload, updated_at
            from kiwoom_order_execution_events
            order by updated_at desc, account_no, order_no
            """
        )
        return self._rows_to_df(rows)

    def table_meta(self, table_name: str, date_col: Optional[str] = None) -> Dict[str, Any]:
        with get_conn(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"select count(*) as c, max(updated_at) as u from {table_name}")
                row = cur.fetchone()
                count = int((row or {}).get("c", 0) or 0)
                updated_at = (row or {}).get("u")
                data_date = None
                if date_col:
                    cur.execute(f"select max({date_col}) as d from {table_name}")
                    row2 = cur.fetchone()
                    data_date = (row2 or {}).get("d")
        return {
            "records": count,
            "updated_at": updated_at.isoformat() if isinstance(updated_at, datetime) else None,
            "data_date": data_date.isoformat() if isinstance(data_date, date) else None,
        }

    def freshness_report(self, max_age_hours: int = 72) -> Dict[str, Any]:
        files: Dict[str, Any] = {}
        errors: List[str] = []
        warnings: List[str] = []

        table_rules = {
            "latest_snapshot.csv": ("naver_latest_snapshot", "trade_date", True),
            "ohlcv_1d.csv": ("naver_ohlcv_1d", "trade_date", True),
            "flows_1d.csv": ("naver_flows_1d", "trade_date", True),
            "news_items.csv": ("naver_news_items", "published_at", False),
            "market_context.csv": ("naver_market_context_1d", "trade_date", False),
            "program_trend.csv": ("naver_program_trend_1d", "trade_date", False),
        }

        now = datetime.now().astimezone()
        required_dates: List[date] = []
        for display_name, (table, date_col, required) in table_rules.items():
            meta = self.table_meta(table, date_col=date_col)
            updated_at_text = meta.get("updated_at")
            updated_at = _to_dt(updated_at_text)
            data_date = _to_date(meta.get("data_date"))
            age_hours = None
            if updated_at is not None:
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=now.tzinfo)
                else:
                    updated_at = updated_at.astimezone(now.tzinfo)
                age_hours = round((now - updated_at).total_seconds() / 3600.0, 2)

            status = "OK"
            reason = ""
            if int(meta.get("records", 0)) <= 0:
                status = "MISSING"
                reason = "table empty"
                (errors if required else warnings).append(f"{display_name} missing")
            elif age_hours is not None and age_hours > max_age_hours:
                status = "STALE"
                reason = f"updated_at older than {max_age_hours}h"
                (errors if required else warnings).append(f"{display_name} stale")

            if required and data_date is not None:
                required_dates.append(data_date)

            files[display_name] = {
                "table": table,
                "exists": int(meta.get("records", 0)) > 0,
                "status": status,
                "reason": reason,
                "required": required,
                "records": int(meta.get("records", 0)),
                "updated_at": updated_at_text,
                "age_hours": age_hours,
                "max_data_time": data_date.isoformat() if data_date else "",
            }

        reference_time = max(required_dates).isoformat() if required_dates else ""
        if errors:
            status = "DATA_MISSING" if any("missing" in e for e in errors) else "DATA_STALE"
        elif warnings:
            status = "OK_WITH_WARNINGS"
        else:
            status = "OK"

        return {
            "status": status,
            "checked_at": now.isoformat(),
            "max_age_hours": int(max_age_hours),
            "reference_data_time": reference_time,
            "summary": "data ready" if status in {"OK", "OK_WITH_WARNINGS"} else "data not ready",
            "errors": errors,
            "warnings": warnings,
            "files": files,
        }

    def save_screener_result(self, payload: Dict[str, Any]) -> str:
        run_id = str(uuid.uuid4())
        run_date = _to_date(payload.get("date")) or date.today()
        by_grade = payload.get("by_grade") if isinstance(payload.get("by_grade"), dict) else {}
        by_market = payload.get("by_market") if isinstance(payload.get("by_market"), dict) else {}
        runtime_meta = payload.get("runtime_meta") if isinstance(payload.get("runtime_meta"), dict) else {}
        processing_time_ms = float(payload.get("processing_time_ms", 0) or 0)
        total_candidates = int(payload.get("total_candidates", 0) or 0)
        filtered_count = int(payload.get("filtered_count", 0) or 0)
        signals = payload.get("signals") if isinstance(payload.get("signals"), list) else []

        insert_run = """
        insert into jongga_runs (
          run_id, run_date, total_candidates, filtered_count, by_grade, by_market,
          runtime_meta, processing_time_ms, source
        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """

        insert_signal = """
        insert into jongga_signals (
          run_id, run_date, signal_rank, stock_code, stock_name, market, sector,
          signal_date, signal_time, grade, score, checklist, news_items, ai_overall,
          foreign_5d, inst_5d, individual_5d, current_price, entry_price, stop_price,
          target_price, r_value, position_size, quantity, r_multiplier, trading_value,
          change_pct, status, created_at
        ) values (
          %s,%s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s
        )
        """

        rows: List[Tuple[Any, ...]] = []
        for idx, s in enumerate(signals, start=1):
            if not isinstance(s, dict):
                continue
            rows.append(
                (
                    run_id,
                    run_date,
                    idx,
                    str(s.get("stock_code", "")),
                    str(s.get("stock_name", "")),
                    str(s.get("market", "")),
                    str(s.get("sector", "")),
                    _to_date(s.get("signal_date")),
                    _to_dt(s.get("signal_time")),
                    str(s.get("grade", "")),
                    json.dumps(s.get("score", {}), ensure_ascii=False),
                    json.dumps(s.get("checklist", {}), ensure_ascii=False),
                    json.dumps(s.get("news_items", []), ensure_ascii=False),
                    json.dumps(s.get("ai_overall", {}), ensure_ascii=False),
                    int(s.get("foreign_5d", 0) or 0),
                    int(s.get("inst_5d", 0) or 0),
                    int(s.get("individual_5d", 0) or 0),
                    float(s.get("current_price", 0) or 0),
                    float(s.get("entry_price", 0) or 0),
                    float(s.get("stop_price", 0) or 0),
                    float(s.get("target_price", 0) or 0),
                    float(s.get("r_value", 0) or 0),
                    float(s.get("position_size", 0) or 0),
                    int(s.get("quantity", 0) or 0),
                    float(s.get("r_multiplier", 0) or 0),
                    int(s.get("trading_value", 0) or 0),
                    float(s.get("change_pct", 0) or 0),
                    str(s.get("status", "")),
                    _to_dt(s.get("created_at")),
                )
            )

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    insert_run,
                    (
                        run_id,
                        run_date,
                        total_candidates,
                        filtered_count,
                        json.dumps(by_grade, ensure_ascii=False),
                        json.dumps(by_market, ensure_ascii=False),
                        json.dumps(runtime_meta, ensure_ascii=False),
                        processing_time_ms,
                        "run_screener",
                    ),
                )
                if rows:
                    cur.executemany(insert_signal, rows)
        return run_id

    def _run_dates(self) -> List[str]:
        rows = self._fetch_rows("select distinct run_date from jongga_runs order by run_date desc")
        out = []
        for r in rows:
            d = r.get("run_date")
            if isinstance(d, date):
                out.append(d.isoformat())
        return out

    def list_run_dates(self) -> List[str]:
        return self._run_dates()

    def _pick_run_id(self, date_arg: Optional[str]) -> Optional[str]:
        if date_arg and date_arg != "latest":
            d = _to_date(date_arg)
            if d is not None:
                row = self._fetch_one(
                    """
                    select run_id from jongga_runs
                    where run_date=%s
                    order by created_at desc
                    limit 1
                    """,
                    (d,),
                )
                if row:
                    return str(row.get("run_id"))

        row = self._fetch_one(
            "select run_id from jongga_runs order by created_at desc limit 1"
        )
        return str(row.get("run_id")) if row else None

    def load_run_payload(self, date_arg: Optional[str] = "latest") -> Optional[Dict[str, Any]]:
        target_date = _to_date(date_arg) if date_arg and str(date_arg) != "latest" else None
        with get_conn(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if target_date is None:
                    cur.execute(
                        """
                        select *
                        from jongga_runs
                        order by created_at desc
                        limit 1
                        """
                    )
                else:
                    cur.execute(
                        """
                        select *
                        from jongga_runs
                        where run_date=%s
                        order by created_at desc
                        limit 1
                        """,
                        (target_date,),
                    )
                run = cur.fetchone()
                if not run:
                    return None

                run_id = run.get("run_id")
                cur.execute(
                    """
                    select signal_rank, *
                    from jongga_signals
                    where run_id=%s
                    order by signal_rank asc
                    """,
                    (run_id,),
                )
                sig_rows = cur.fetchall()

        signals: List[Dict[str, Any]] = []
        for r in sig_rows:
            def _decode(v: Any, default: Any) -> Any:
                if v is None:
                    return default
                if isinstance(v, (dict, list)):
                    return v
                try:
                    return json.loads(v)
                except Exception:
                    return default

            signal_date = r.get("signal_date")
            signal_time = r.get("signal_time")
            created_at = r.get("created_at")
            signals.append(
                {
                    "signal_rank": int(r.get("signal_rank", 0) or 0),
                    "stock_code": str(r.get("stock_code", "")),
                    "stock_name": str(r.get("stock_name", "")),
                    "market": str(r.get("market", "")),
                    "sector": str(r.get("sector", "")),
                    "signal_date": signal_date.isoformat() if isinstance(signal_date, date) else "",
                    "signal_time": signal_time.isoformat() if isinstance(signal_time, datetime) else "",
                    "grade": str(r.get("grade", "")),
                    "score": _decode(r.get("score"), {}),
                    "checklist": _decode(r.get("checklist"), {}),
                    "news_items": _decode(r.get("news_items"), []),
                    "ai_overall": _decode(r.get("ai_overall"), {}),
                    "foreign_5d": int(r.get("foreign_5d", 0) or 0),
                    "inst_5d": int(r.get("inst_5d", 0) or 0),
                    "individual_5d": int(r.get("individual_5d", 0) or 0),
                    "current_price": float(r.get("current_price", 0) or 0),
                    "entry_price": float(r.get("entry_price", 0) or 0),
                    "stop_price": float(r.get("stop_price", 0) or 0),
                    "target_price": float(r.get("target_price", 0) or 0),
                    "r_value": float(r.get("r_value", 0) or 0),
                    "position_size": float(r.get("position_size", 0) or 0),
                    "quantity": int(r.get("quantity", 0) or 0),
                    "r_multiplier": float(r.get("r_multiplier", 0) or 0),
                    "trading_value": int(r.get("trading_value", 0) or 0),
                    "change_pct": float(r.get("change_pct", 0) or 0),
                    "status": str(r.get("status", "")),
                    "created_at": created_at.isoformat() if isinstance(created_at, datetime) else "",
                }
            )

        run_date = run.get("run_date")
        created_at = run.get("created_at")
        by_grade = run.get("by_grade") if isinstance(run.get("by_grade"), dict) else {}
        by_market = run.get("by_market") if isinstance(run.get("by_market"), dict) else {}
        runtime_meta = run.get("runtime_meta") if isinstance(run.get("runtime_meta"), dict) else {}
        return {
            "date": run_date.isoformat() if isinstance(run_date, date) else date.today().isoformat(),
            "total_candidates": int(run.get("total_candidates", 0) or 0),
            "filtered_count": int(run.get("filtered_count", 0) or 0),
            "signals": signals,
            "by_grade": by_grade,
            "by_market": by_market,
            "runtime_meta": runtime_meta,
            "processing_time_ms": float(run.get("processing_time_ms", 0) or 0),
            "updated_at": created_at.isoformat() if isinstance(created_at, datetime) else datetime.now().isoformat(),
        }

    def ranked_dataframe(self, date_arg: Optional[str] = "latest") -> pd.DataFrame:
        payload = self.load_run_payload(date_arg)
        if not payload:
            return pd.DataFrame()
        rows = []
        for s in payload.get("signals", []):
            score = s.get("score") if isinstance(s.get("score"), dict) else {}
            checklist = s.get("checklist") if isinstance(s.get("checklist"), dict) else {}
            rows.append(
                {
                    "date": payload.get("date", ""),
                    "ticker": str(s.get("stock_code", "")).zfill(6),
                    "name": str(s.get("stock_name", "")),
                    "market": str(s.get("market", "")),
                    "grade": str(s.get("grade", "C")).upper(),
                    "score_total": int(score.get("total", 0) or 0),
                    "score_news": int(score.get("news", 0) or 0),
                    "score_supply": int(score.get("supply", 0) or 0),
                    "score_volume": int(score.get("volume", 0) or 0),
                    "score_chart": int(score.get("chart", 0) or 0),
                    "score_candle": int(score.get("candle", 0) or 0),
                    "score_consolidation": int(score.get("consolidation", 0) or 0),
                    "score_market": int(score.get("market", 0) or 0),
                    "score_program": int(score.get("program", 0) or 0),
                    "change_pct": float(s.get("change_pct", 0) or 0),
                    "trading_value": int(s.get("trading_value", 0) or 0),
                    "has_news": bool(checklist.get("has_news", False)),
                    "supply_positive": bool(checklist.get("supply_positive", False)),
                    "is_breakout": bool(checklist.get("is_breakout", False)),
                    "is_new_high": bool(checklist.get("is_new_high", False)),
                    "market_supportive": bool(checklist.get("market_supportive", False)),
                    "program_supportive": bool(checklist.get("program_supportive", False)),
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["score_total", "trading_value"], ascending=[False, False]).reset_index(drop=True)
        return df

    def preview_for_task(self, task_id: str, limit: int) -> Dict[str, Any]:
        task_map = {
            "daily_prices": self.load_ohlcv_df,
            "institutional_trend": self.load_flows_df,
            "ai_analysis": self.load_news_df,
            "market_context": self.load_market_context_df,
            "program_trend": self.load_program_trend_df,
            "vcp_signals": self.load_vcp_df,
            "ai_jongga_v2": lambda: self.ranked_dataframe("latest"),
        }
        loader = task_map.get(task_id)
        if loader is None:
            return {"columns": [], "rows": []}

        df = loader()
        if df.empty:
            return {"columns": [], "rows": []}

        rows_limit = max(1, int(limit or 20))
        date_col = None
        for c in ["date", "published_at", "signal_date", "trade_date"]:
            if c in df.columns:
                date_col = c
                break

        if date_col is not None:
            parsed = pd.to_datetime(df[date_col], errors="coerce")
            df = df.assign(__dt=parsed).sort_values("__dt", ascending=False, na_position="last").drop(columns=["__dt"])

        df = df.head(rows_limit)
        return {
            "columns": [str(c) for c in df.columns],
            "rows": df.fillna("").to_dict(orient="records"),
        }

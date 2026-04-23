from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from providers.kiwoom_client import KiwoomAPIError, KiwoomRESTClient, effective_venue, venue_stock_code
from supabase_py.db import is_supabase_backend
from supabase_py.repository import SupabaseRepository


def _to_int(value: Any) -> int:
    try:
        text = str(value or "").replace(",", "").strip()
        if not text:
            return 0
        sign = -1 if text.startswith("-") or text.startswith("--") else 1
        digits = "".join(ch for ch in text if ch.isdigit())
        return sign * int(digits or "0")
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        text = str(value or "").replace(",", "").strip()
        if not text:
            return 0.0
        sign = -1 if text.startswith("-") or text.startswith("--") else 1
        digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
        return sign * float(digits or "0")
    except Exception:
        return 0.0


def _to_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _load_universe(repo: SupabaseRepository, limit_per_market: int) -> pd.DataFrame:
    universe = repo.load_universe_df()
    if universe.empty:
        raise RuntimeError("kiwoom source requires a base universe in DB")
    if "market_cap_eok" in universe.columns:
        universe["market_cap_eok"] = pd.to_numeric(universe["market_cap_eok"], errors="coerce").fillna(0)
        universe = universe.sort_values(["market", "market_cap_eok"], ascending=[True, False])
    pieces = []
    for market in ["KOSPI", "KOSDAQ"]:
        part = universe[universe["market"].astype(str).str.upper() == market].head(limit_per_market)
        if not part.empty:
            pieces.append(part)
    return pd.concat(pieces, ignore_index=True) if pieces else universe.head(limit_per_market * 2).reset_index(drop=True)


def _paginate_rows(client: KiwoomRESTClient, path: str, api_id: str, payload: dict[str, Any], list_key: str, max_pages: int = 4) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for body in client.paginate(path, api_id, payload, max_pages=max_pages):
        items = body.get(list_key)
        if isinstance(items, list):
            rows.extend([item for item in items if isinstance(item, dict)])
    return rows


async def _async_paginate_rows(
    client: "AsyncKiwoomClient",
    path: str,
    api_id: str,
    payload: dict[str, Any],
    list_key: str,
    max_pages: int = 4,
) -> list[dict[str, Any]]:
    """AsyncKiwoomClient용 paginate. 페이징이 없는 경우 1회만 호출."""
    rows: list[dict[str, Any]] = []
    cont_yn = "N"
    next_key = ""
    for _ in range(max_pages):
        res = await client.request(path, api_id, payload, cont_yn=cont_yn, next_key=next_key)
        items = res.body.get(list_key)
        if isinstance(items, list):
            rows.extend([item for item in items if isinstance(item, dict)])
        cont_yn = str(res.headers.get("cont-yn", "N") or "N").upper()
        next_key = str(res.headers.get("next-key", "") or "")
        if cont_yn != "Y" or not next_key:
            break
    return rows


async def collect_ohlcv_async(repo: SupabaseRepository, limit_per_market: int, concurrency: int = 8) -> pd.DataFrame:
    """Design Ref: Design §10 Phase H Part 2 — ohlcv 수집 병렬화
    기존 직렬(200 tickers × 0.22s = 44s+) → asyncio 세마포어=8 → ~6-10초 기대
    """
    from providers.kiwoom_client_async import AsyncKiwoomClient

    base_date = date.today().strftime("%Y%m%d")
    venue, _ = effective_venue()
    universe = _load_universe(repo, limit_per_market)
    ticker_meta: list[tuple[str, str, str, int]] = []
    for _, row in universe.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        ticker_meta.append((
            ticker,
            str(row.get("market", "")).upper(),
            str(row.get("name", "")),
            _to_int(row.get("market_cap_eok")),
        ))

    async with AsyncKiwoomClient(concurrency=concurrency) as client:
        async def _fetch_one(ticker: str) -> list[dict[str, Any]]:
            try:
                return await _async_paginate_rows(
                    client,
                    "/api/dostk/chart",
                    "ka10081",
                    {"stk_cd": venue_stock_code(ticker, venue), "base_dt": base_date, "upd_stkpc_tp": "1"},
                    "stk_dt_pole_chart_qry",
                    max_pages=3,
                )
            except Exception:
                return []

        results = await asyncio.gather(*[_fetch_one(t) for t, _, _, _ in ticker_meta])

    rows: list[dict[str, Any]] = []
    for (ticker, market, name, marcap), items in zip(ticker_meta, results):
        for item in items:
            trade_date = str(item.get("dt", "")).strip()
            if len(trade_date) != 8:
                continue
            rows.append({
                "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                "ticker": ticker,
                "name": name,
                "market": market,
                "open": _to_float(item.get("open_pric")),
                "high": _to_float(item.get("high_pric")),
                "low": _to_float(item.get("low_pric")),
                "close": _to_float(item.get("cur_prc")),
                "volume": _to_int(item.get("trde_qty")),
                "trading_value": _to_int(item.get("trde_prica")) * 1_000_000,
                "foreign_retention_rate": 0.0,
                "market_cap_eok": marcap,
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["date", "ticker"]).sort_values(["ticker", "date"]).reset_index(drop=True)


async def collect_flows_async(repo: SupabaseRepository, limit_per_market: int, concurrency: int = 8) -> pd.DataFrame:
    """Design Ref: Design §10 Phase H Part 2 — flows 병렬 수집"""
    from providers.kiwoom_client_async import AsyncKiwoomClient

    base_date = date.today().strftime("%Y%m%d")
    venue, _ = effective_venue()
    universe = _load_universe(repo, limit_per_market)
    tickers = [str(row.get("ticker", "")).zfill(6) for _, row in universe.iterrows() if str(row.get("ticker", "")).zfill(6)]

    async with AsyncKiwoomClient(concurrency=concurrency) as client:
        async def _fetch_one(ticker: str) -> list[dict[str, Any]]:
            try:
                return await _async_paginate_rows(
                    client,
                    "/api/dostk/chart",
                    "ka10060",
                    {"dt": base_date, "stk_cd": venue_stock_code(ticker, venue), "amt_qty_tp": "2", "trde_tp": "0", "unit_tp": "1"},
                    "stk_invsr_orgn_chart",
                    max_pages=2,
                )
            except Exception:
                return []

        results = await asyncio.gather(*[_fetch_one(t) for t in tickers])

    rows: list[dict[str, Any]] = []
    for ticker, items in zip(tickers, results):
        for item in items:
            trade_date = str(item.get("dt", "")).strip()
            if len(trade_date) != 8:
                continue
            foreign = _to_int(item.get("frgnr_invsr"))
            inst = _to_int(item.get("orgn"))
            individual = _to_int(item.get("ind_invsr"))
            rows.append({
                "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                "ticker": ticker,
                "foreign_net_buy": foreign,
                "inst_net_buy": inst,
                "retail_net_buy": individual if individual else -(foreign + inst),
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["date", "ticker"]).sort_values(["ticker", "date"]).reset_index(drop=True)


def collect_ohlcv(repo: SupabaseRepository, client: KiwoomRESTClient, limit_per_market: int) -> pd.DataFrame:
    base_date = date.today().strftime("%Y%m%d")
    venue, _ = effective_venue()
    universe = _load_universe(repo, limit_per_market)
    rows: list[dict[str, Any]] = []
    for _, row in universe.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        market = str(row.get("market", "")).upper()
        name = str(row.get("name", ""))
        if not ticker:
            continue
        items = _paginate_rows(
            client,
            "/api/dostk/chart",
            "ka10081",
            {
                "stk_cd": venue_stock_code(ticker, venue),
                "base_dt": base_date,
                "upd_stkpc_tp": "1",
            },
            "stk_dt_pole_chart_qry",
            max_pages=3,
        )
        for item in items:
            trade_date = str(item.get("dt", "")).strip()
            if len(trade_date) != 8:
                continue
            rows.append(
                {
                    "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "open": _to_float(item.get("open_pric")),
                    "high": _to_float(item.get("high_pric")),
                    "low": _to_float(item.get("low_pric")),
                    "close": _to_float(item.get("cur_prc")),
                    "volume": _to_int(item.get("trde_qty")),
                    "trading_value": _to_int(item.get("trde_prica")) * 1_000_000,
                    "foreign_retention_rate": 0.0,
                    "market_cap_eok": _to_int(row.get("market_cap_eok")),
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["date", "ticker"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    return df


def collect_flows(repo: SupabaseRepository, client: KiwoomRESTClient, limit_per_market: int) -> pd.DataFrame:
    base_date = date.today().strftime("%Y%m%d")
    venue, _ = effective_venue()
    universe = _load_universe(repo, limit_per_market)
    rows: list[dict[str, Any]] = []
    for _, row in universe.iterrows():
        ticker = str(row.get("ticker", "")).zfill(6)
        if not ticker:
            continue
        items = _paginate_rows(
            client,
            "/api/dostk/chart",
            "ka10060",
            {
                "dt": base_date,
                "stk_cd": venue_stock_code(ticker, venue),
                "amt_qty_tp": "2",
                "trde_tp": "0",
                "unit_tp": "1",
            },
            "stk_invsr_orgn_chart",
            max_pages=2,
        )
        for item in items:
            trade_date = str(item.get("dt", "")).strip()
            if len(trade_date) != 8:
                continue
            foreign = _to_int(item.get("frgnr_invsr"))
            inst = _to_int(item.get("orgn"))
            individual = _to_int(item.get("ind_invsr"))
            rows.append(
                {
                    "date": f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                    "ticker": ticker,
                    "foreign_net_buy": foreign,
                    "inst_net_buy": inst,
                    "retail_net_buy": individual if individual else -(foreign + inst),
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["date", "ticker"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    return df


def _program_market_code(market: str, venue: str) -> str:
    market = market.upper()
    if market == "KOSPI":
        return {"KRX": "P00101", "NXT": "P001_NX01"}.get(venue, "P00101")
    return {"KRX": "P10102", "NXT": "P101_NX02"}.get(venue, "P10102")


def _program_market_short(market: str) -> str:
    return "0" if str(market or "").upper() == "KOSPI" else "1"


def collect_program_trend(client: KiwoomRESTClient) -> pd.DataFrame:
    today = date.today()
    venue, venue_code = effective_venue()
    rows: list[dict[str, Any]] = []
    for market in ["KOSPI", "KOSDAQ"]:
        items = _paginate_rows(
            client,
            "/api/dostk/mrkcond",
            "ka90005",
            {
                "date": today.strftime("%Y%m%d"),
                "amt_qty_tp": "1",
                "mrkt_tp": _program_market_code(market, venue),
                "min_tic_tp": "1",
                "stex_tp": venue_code,
            },
            "prm_trde_trnsn",
            max_pages=1,
        )
        if not items:
            continue
        latest = items[0]
        rows.append(
            {
                "trade_date": today.isoformat(),
                "market": market,
                "market_status": venue,
                "arbitrage_buy": _to_int(latest.get("dfrt_trde_buy")) * 1_000_000,
                "arbitrage_sell": _to_int(latest.get("dfrt_trde_sel")) * 1_000_000,
                "arbitrage_net": _to_int(latest.get("dfrt_trde_netprps")) * 1_000_000,
                "non_arbitrage_buy": _to_int(latest.get("ndiffpro_trde_buy")) * 1_000_000,
                "non_arbitrage_sell": _to_int(latest.get("ndiffpro_trde_sel")) * 1_000_000,
                "non_arbitrage_net": _to_int(latest.get("ndiffpro_trde_netprps")) * 1_000_000,
                "total_buy": _to_int(latest.get("all_buy")) * 1_000_000,
                "total_sell": _to_int(latest.get("all_sel")) * 1_000_000,
                "total_net": _to_int(latest.get("all_netprps")) * 1_000_000,
                "snapshot_time": _to_dt(str(today.strftime("%Y%m%d")) + str(latest.get("cntr_tm", ""))),
            }
        )
    return pd.DataFrame(rows)


def _build_priority_candidates(repo: SupabaseRepository, limit: int) -> pd.DataFrame:
    snapshot = repo.load_snapshot_df()
    if snapshot.empty:
        return pd.DataFrame()
    snapshot["trading_value"] = pd.to_numeric(snapshot["trading_value"], errors="coerce").fillna(0)
    snapshot["ticker"] = snapshot["ticker"].astype(str).str.zfill(6)
    ranked_snapshot = snapshot.sort_values(["trading_value", "change_pct"], ascending=[False, False]).copy()

    latest_payload = repo.load_run_payload("latest") or {}
    latest_signals = latest_payload.get("signals") if isinstance(latest_payload.get("signals"), list) else []
    signal_rows: list[dict[str, Any]] = []
    for item in latest_signals:
        if not isinstance(item, dict):
            continue
        base_grade = str((item.get("ai_overall") or {}).get("base_grade") or item.get("grade") or "C").upper()
        if base_grade not in {"S", "A", "B"}:
            continue
        signal_rows.append(
            {
                "ticker": str(item.get("stock_code", "")).zfill(6),
                "priority": 0,
            }
        )

    ranked_snapshot["priority"] = 1
    candidate_pool = ranked_snapshot[["ticker", "name", "market", "trading_value", "change_pct", "priority"]].copy()
    if signal_rows:
        signal_df = pd.DataFrame(signal_rows)
        prioritized = signal_df[["ticker"]].merge(candidate_pool.drop(columns=["priority"]), on="ticker", how="left")
        prioritized["priority"] = 0
        extra_candidates = ranked_snapshot[~ranked_snapshot["ticker"].isin(signal_df["ticker"].tolist())][["ticker", "name", "market", "trading_value", "change_pct", "priority"]]
        candidate_pool = pd.concat([prioritized, extra_candidates], ignore_index=True)
    candidate_pool = candidate_pool.drop_duplicates(subset=["ticker"], keep="first")
    return candidate_pool.sort_values(["priority", "trading_value", "change_pct"], ascending=[True, False, False]).head(limit)


def _parse_program_time(value: Any, trade_date: date) -> datetime | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) >= 14:
        return _to_dt(digits[:14])
    if len(digits) >= 6:
        return _to_dt(trade_date.strftime("%Y%m%d") + digits[:6])
    return None


def _collect_stock_program_payload(
    client: KiwoomRESTClient,
    *,
    ticker: str,
    market: str,
    venue: str,
    trade_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    code = venue_stock_code(ticker, venue)
    intraday_body = client.request(
        "/api/dostk/mrkcond",
        "ka90008",
        {
            "stk_cd": code,
            "date": trade_date.strftime("%Y%m%d"),
            "amt_qty_tp": "1",
        },
    ).body
    daily_body = client.request(
        "/api/dostk/mrkcond",
        "ka90013",
        {
            "stk_cd": code,
            "date": trade_date.strftime("%Y%m%d"),
            "amt_qty_tp": "1",
            "mrkt_tp": _program_market_short(market),
        },
    ).body
    intraday_rows = intraday_body.get("stk_tm_prm_trde_trnsn") if isinstance(intraday_body.get("stk_tm_prm_trde_trnsn"), list) else []
    daily_rows = daily_body.get("stk_daly_prm_trde_trnsn") if isinstance(daily_body.get("stk_daly_prm_trde_trnsn"), list) else []
    return intraday_rows, daily_rows


def collect_stock_program_data(repo: SupabaseRepository, client: KiwoomRESTClient, limit: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    today = date.today()
    venue, _ = effective_venue()
    candidates = _build_priority_candidates(repo, limit)
    if candidates.empty:
        return pd.DataFrame(), pd.DataFrame()

    latest_rows: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []

    for _, item in candidates.iterrows():
        ticker = str(item.get("ticker", "")).zfill(6)
        market = str(item.get("market", "")).upper()
        name = str(item.get("name", ""))
        if not ticker:
            continue
        try:
            intraday_rows, daily_items = _collect_stock_program_payload(
                client,
                ticker=ticker,
                market=market,
                venue=venue,
                trade_date=today,
            )
        except KiwoomAPIError:
            continue

        intraday_rows = [row for row in intraday_rows if isinstance(row, dict)]
        if intraday_rows:
            normalized: list[dict[str, Any]] = []
            for row in intraday_rows:
                row_time = _parse_program_time(row.get("tm"), today)
                if row_time is None or row_time.date() != today:
                    continue
                normalized.append({"time": row_time, "raw": row})
            normalized.sort(key=lambda entry: entry["time"])
            if normalized:
                latest = normalized[-1]["raw"]
                latest_time = normalized[-1]["time"]
                latest_net_amt = _to_int(latest.get("prm_netprps_amt")) * 1_000_000
                latest_net_qty = _to_int(latest.get("prm_netprps_qty"))

                baseline_10 = next((entry["raw"] for entry in normalized if latest_time - entry["time"] >= timedelta(minutes=10)), normalized[0]["raw"])
                baseline_30 = next((entry["raw"] for entry in normalized if latest_time - entry["time"] >= timedelta(minutes=30)), normalized[0]["raw"])
                latest_rows.append(
                    {
                        "trade_date": today.isoformat(),
                        "ticker": ticker,
                        "stock_name": name,
                        "market": market,
                        "venue": venue,
                        "latest_time": latest_time.isoformat(),
                        "current_price": _to_float(latest.get("cur_prc")),
                        "change_pct": _to_float(latest.get("flu_rt")),
                        "program_sell_amt": _to_int(latest.get("prm_sell_amt")) * 1_000_000,
                        "program_buy_amt": _to_int(latest.get("prm_buy_amt")) * 1_000_000,
                        "program_net_buy_amt": latest_net_amt,
                        "program_sell_qty": _to_int(latest.get("prm_sell_qty")),
                        "program_buy_qty": _to_int(latest.get("prm_buy_qty")),
                        "program_net_buy_qty": latest_net_qty,
                        "delta_10m_amt": latest_net_amt - (_to_int(baseline_10.get("prm_netprps_amt")) * 1_000_000),
                        "delta_30m_amt": latest_net_amt - (_to_int(baseline_30.get("prm_netprps_amt")) * 1_000_000),
                        "delta_10m_qty": latest_net_qty - _to_int(baseline_10.get("prm_netprps_qty")),
                        "delta_30m_qty": latest_net_qty - _to_int(baseline_30.get("prm_netprps_qty")),
                    }
                )

        for row in daily_items:
            if not isinstance(row, dict):
                continue
            trade_date_raw = str(row.get("dt", "") or "")
            if len(trade_date_raw) != 8:
                continue
            daily_rows.append(
                {
                    "trade_date": f"{trade_date_raw[:4]}-{trade_date_raw[4:6]}-{trade_date_raw[6:8]}",
                    "ticker": ticker,
                    "stock_name": name,
                    "venue": str(row.get("stex_tp", venue) or venue),
                    "current_price": _to_float(row.get("cur_prc")),
                    "change_pct": _to_float(row.get("flu_rt")),
                    "trade_volume": _to_int(row.get("trde_qty")),
                    "program_sell_amt": _to_int(row.get("prm_sell_amt")) * 1_000_000,
                    "program_buy_amt": _to_int(row.get("prm_buy_amt")) * 1_000_000,
                    "program_net_buy_amt": _to_int(row.get("prm_netprps_amt")) * 1_000_000,
                    "program_sell_qty": _to_int(row.get("prm_sell_qty")),
                    "program_buy_qty": _to_int(row.get("prm_buy_qty")),
                    "program_net_buy_qty": _to_int(row.get("prm_netprps_qty")),
                }
            )

    latest_df = pd.DataFrame(latest_rows).drop_duplicates(subset=["trade_date", "ticker"]).reset_index(drop=True) if latest_rows else pd.DataFrame()
    daily_df = pd.DataFrame(daily_rows).drop_duplicates(subset=["trade_date", "ticker"]).sort_values(["ticker", "trade_date"]).reset_index(drop=True) if daily_rows else pd.DataFrame()
    return latest_df, daily_df


def _derive_minute_pattern(minute_rows: list[dict[str, Any]]) -> tuple[str, float]:
    if len(minute_rows) < 6:
        return "insufficient", 0.0
    candles = []
    for item in minute_rows[:12]:
        candles.append(
            {
                "close": _to_float(item.get("cur_prc")),
                "open": _to_float(item.get("open_pric")),
                "high": _to_float(item.get("high_pric")),
                "low": _to_float(item.get("low_pric")),
                "volume": _to_int(item.get("trde_qty")),
            }
        )
    latest = candles[0]
    prior = candles[1:6]
    prior_high = max(c["high"] for c in prior)
    prior_low = min(c["low"] for c in prior)
    avg_volume = sum(c["volume"] for c in prior) / max(len(prior), 1)
    breakout_score = 0.0
    if latest["close"] >= prior_high and latest["volume"] > avg_volume * 1.2:
        breakout_score = round((latest["close"] - prior_high) / max(prior_high, 1) * 100, 2)
        return "rebreakout", breakout_score
    if latest["high"] > prior_high and latest["close"] < prior_high:
        breakout_score = round((latest["close"] - prior_high) / max(prior_high, 1) * 100, 2)
        return "failed_breakout", breakout_score
    if latest["close"] <= prior_low:
        breakout_score = round((latest["close"] - prior_low) / max(prior_low, 1) * 100, 2)
        return "breakdown", breakout_score
    return "range", breakout_score


def collect_intraday_features(repo: SupabaseRepository, client: KiwoomRESTClient, limit: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    today = date.today().isoformat()
    collected_at = datetime.now()
    venue, _ = effective_venue()
    snapshot = repo.load_snapshot_df()
    if snapshot.empty:
        return pd.DataFrame(), pd.DataFrame()
    snapshot["trading_value"] = pd.to_numeric(snapshot["trading_value"], errors="coerce").fillna(0)
    snapshot["ticker"] = snapshot["ticker"].astype(str).str.zfill(6)
    ranked_snapshot = snapshot.sort_values(["trading_value", "change_pct"], ascending=[False, False]).copy()

    latest_payload = repo.load_run_payload("latest") or {}
    latest_signals = latest_payload.get("signals") if isinstance(latest_payload.get("signals"), list) else []
    signal_rows: list[dict[str, Any]] = []
    for item in latest_signals:
        if not isinstance(item, dict):
            continue
        base_grade = str((item.get("ai_overall") or {}).get("base_grade") or item.get("grade") or "C").upper()
        if base_grade not in {"S", "A", "B"}:
            continue
        signal_rows.append(
            {
                "ticker": str(item.get("stock_code", "")).zfill(6),
                "priority": 0,
            }
        )

    ranked_snapshot["priority"] = 1
    candidate_pool = ranked_snapshot[["ticker", "name", "market", "trading_value", "change_pct", "priority"]].copy()
    if signal_rows:
        signal_df = pd.DataFrame(signal_rows)
        prioritized = signal_df[["ticker"]].merge(candidate_pool.drop(columns=["priority"]), on="ticker", how="left")
        prioritized["priority"] = 0
        extra_candidates = ranked_snapshot[~ranked_snapshot["ticker"].isin(signal_df["ticker"].tolist())][["ticker", "name", "market", "trading_value", "change_pct", "priority"]]
        candidate_pool = pd.concat([prioritized, extra_candidates], ignore_index=True)
    candidate_pool = candidate_pool.drop_duplicates(subset=["ticker"], keep="first")
    candidates = candidate_pool.sort_values(["priority", "trading_value", "change_pct"], ascending=[True, False, False]).head(limit)
    condition_hits = pd.DataFrame(columns=["trade_date", "ticker", "condition_seq", "condition_name", "hit_count", "first_seen_at", "last_seen_at"])

    rows: list[dict[str, Any]] = []
    for _, item in candidates.iterrows():
        ticker = str(item.get("ticker", "")).zfill(6)
        market = str(item.get("market", "")).upper()
        if not ticker:
            continue
        code = venue_stock_code(ticker, venue)
        try:
            orderbook = client.request("/api/dostk/mrkcond", "ka10004", {"stk_cd": code}).body
            strength_body = client.request("/api/dostk/mrkcond", "ka10046", {"stk_cd": code}).body
            minute_body = client.request(
                "/api/dostk/chart",
                "ka10080",
                {"stk_cd": code, "tic_scope": "5", "upd_stkpc_tp": "1", "base_dt": date.today().strftime("%Y%m%d")},
            ).body
        except KiwoomAPIError:
            continue

        strength_rows = strength_body.get("cntr_str_tm") if isinstance(strength_body.get("cntr_str_tm"), list) else []
        minute_rows = minute_body.get("stk_min_pole_chart_qry") if isinstance(minute_body.get("stk_min_pole_chart_qry"), list) else []
        if not strength_rows:
            continue

        latest_strength = strength_rows[0]
        minute_pattern, minute_breakout_score = _derive_minute_pattern(minute_rows)
        bid_total = _to_int(orderbook.get("tot_buy_req"))
        ask_total = _to_int(orderbook.get("tot_sel_req"))
        denom = max(bid_total + ask_total, 1)
        rows.append(
            {
                "trade_date": today,
                "snapshot_time": _to_dt(str(today.replace('-', '')) + str(latest_strength.get("cntr_tm", ""))) or collected_at,
                "ticker": ticker,
                "stock_name": str(item.get("name", "")),
                "market": market,
                "venue": venue,
                "current_price": _to_float(latest_strength.get("cur_prc")),
                "change_pct": _to_float(latest_strength.get("flu_rt")),
                "bid_total": bid_total,
                "ask_total": ask_total,
                "orderbook_imbalance": round((bid_total - ask_total) / denom, 4),
                "execution_strength": _to_float(latest_strength.get("cntr_str")),
                "tick_volume": _to_int(latest_strength.get("trde_qty")),
                "minute_pattern": minute_pattern,
                "minute_breakout_score": minute_breakout_score,
                "volume_surge_ratio": round(
                    _to_int(latest_strength.get("trde_qty")) / max(sum(_to_int(x.get("trde_qty")) for x in strength_rows[1:6]) / max(len(strength_rows[1:6]), 1), 1),
                    2,
                ),
                "orderbook_surge_ratio": round(bid_total / max(ask_total, 1), 2),
                "vi_active": False,
                "vi_type": "",
                "condition_hit_count": 0,
                "condition_names": [],
                "acc_trade_value": _to_int(latest_strength.get("acc_trde_prica")) * 1_000_000,
                "acc_trade_volume": _to_int(latest_strength.get("acc_trde_qty")),
            }
        )
    return pd.DataFrame(rows), condition_hits


def build_snapshot(universe: pd.DataFrame, ohlcv: pd.DataFrame, intraday: pd.DataFrame) -> pd.DataFrame:
    if ohlcv.empty:
        return pd.DataFrame()
    frame = ohlcv.sort_values(["ticker", "date"]).copy()
    frame["prev_close"] = frame.groupby("ticker")["close"].shift(1)
    latest = frame.groupby("ticker", as_index=False).tail(1).copy()
    latest["change_pct"] = (
        (latest["close"] - latest["prev_close"]) / latest["prev_close"].replace(0, pd.NA) * 100
    ).fillna(0.0)
    if "market_cap_eok" not in latest.columns:
        merged = latest.merge(universe[["ticker", "name", "market", "market_cap_eok"]], on="ticker", how="left")
    else:
        merged = latest
    if intraday is not None and not intraday.empty:
        intraday_view = intraday[["ticker", "current_price", "change_pct", "acc_trade_value", "acc_trade_volume"]].copy()
        intraday_view = intraday_view.rename(
            columns={
                "current_price": "intraday_price",
                "change_pct": "intraday_change_pct",
                "acc_trade_value": "intraday_trading_value",
                "acc_trade_volume": "intraday_volume",
            }
        )
        merged = merged.merge(intraday_view, on="ticker", how="left")
        merged["close"] = merged["intraday_price"].fillna(merged["close"])
        merged["change_pct"] = merged["intraday_change_pct"].fillna(merged.get("change_pct", 0.0))
        merged["trading_value"] = merged["intraday_trading_value"].fillna(merged["trading_value"])
        merged["volume"] = merged["intraday_volume"].fillna(merged["volume"])
    else:
        merged["change_pct"] = merged["change_pct"].fillna(0.0)
    return merged[["date", "ticker", "name", "market", "close", "change_pct", "volume", "trading_value", "market_cap_eok"]].sort_values(["change_pct", "trading_value"], ascending=[False, False]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kiwoom bootstrap collector for closing-bet system")
    parser.add_argument("--steps", default="ohlcv,flows,program,stock_program,intraday,snapshot")
    parser.add_argument("--limit-per-market", type=int, default=100)
    parser.add_argument("--intraday-top", type=int, default=60)
    parser.add_argument("--refresh-today", default="1")
    args = parser.parse_args()

    if not is_supabase_backend():
        raise SystemExit("DB backend is required. Set STORAGE_BACKEND=supabase and SUPABASE_DATABASE_URL")

    steps = [step.strip().lower() for step in str(args.steps or "").split(",") if step.strip()]
    repo = SupabaseRepository.from_env()
    rest = KiwoomRESTClient()

    universe = _load_universe(repo, args.limit_per_market)
    ohlcv = pd.DataFrame()
    intraday = pd.DataFrame()

    # Design Ref: Design §10 Phase H Part 2 — env KIWOOM_ASYNC=1 로 병렬화 opt-in
    # 기본값은 sync (backward compat). async 경로가 안정화된 뒤 default 전환.
    async_enabled = str(os.getenv("KIWOOM_ASYNC", "")).strip() in {"1", "true", "yes"}
    async_concurrency = max(1, min(32, int(os.getenv("KIWOOM_ASYNC_CONCURRENCY", "8") or 8)))
    if async_enabled:
        print(f"[kiwoom] ASYNC MODE enabled (concurrency={async_concurrency})")

    if "ohlcv" in steps:
        print("[kiwoom] ohlcv collecting...")
        import time as _t
        _s = _t.time()
        if async_enabled:
            ohlcv = asyncio.run(collect_ohlcv_async(repo, args.limit_per_market, concurrency=async_concurrency))
        else:
            ohlcv = collect_ohlcv(repo, rest, args.limit_per_market)
        if not ohlcv.empty:
            repo.upsert_ohlcv(ohlcv)
            print(f"  ohlcv rows: {len(ohlcv)}  ({_t.time()-_s:.1f}s)")

    if "flows" in steps:
        print("[kiwoom] flows collecting...")
        import time as _t
        _s = _t.time()
        if async_enabled:
            flows = asyncio.run(collect_flows_async(repo, args.limit_per_market, concurrency=async_concurrency))
        else:
            flows = collect_flows(repo, rest, args.limit_per_market)
        if not flows.empty:
            repo.upsert_flows(flows)
            print(f"  flows rows: {len(flows)}  ({_t.time()-_s:.1f}s)")

    if "program" in steps:
        print("[kiwoom] program trend collecting...")
        program = collect_program_trend(rest)
        if not program.empty:
            repo.upsert_program_trend(program)
            repo.upsert_kiwoom_program_snapshots(program)
            print(f"  program rows: {len(program)}")

    if "stock_program" in steps:
        print("[kiwoom] stock program collecting...")
        stock_program_latest, stock_program_daily = collect_stock_program_data(repo, rest, args.intraday_top)
        if not stock_program_latest.empty:
            repo.upsert_kiwoom_stock_program_latest(stock_program_latest)
            print(f"  stock program latest rows: {len(stock_program_latest)}")
        if not stock_program_daily.empty:
            repo.upsert_kiwoom_stock_program_daily(stock_program_daily)
            print(f"  stock program daily rows: {len(stock_program_daily)}")

    if "intraday" in steps:
        print("[kiwoom] intraday features collecting...")
        intraday, condition_hits = collect_intraday_features(repo, rest, args.intraday_top)
        if not intraday.empty:
            repo.upsert_kiwoom_intraday_features(intraday)
            repo.upsert_kiwoom_intraday_snapshots(intraday)
            print(f"  intraday rows: {len(intraday)}")
        if condition_hits is not None and not condition_hits.empty:
            repo.upsert_kiwoom_condition_hits(condition_hits)
            print(f"  condition hits: {len(condition_hits)}")

    if "snapshot" in steps:
        print("[kiwoom] latest snapshot building...")
        if ohlcv.empty:
            ohlcv = repo.load_ohlcv_df()
        snap = build_snapshot(universe, ohlcv, intraday)
        if not snap.empty:
            repo.upsert_snapshot(snap)
            print(f"  snapshot rows: {len(snap)}")

    print("\nDone.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supabase_py.db import is_supabase_backend
from supabase_py.repository import SupabaseRepository
from engine.krx_filters import is_etf_or_etn_name
from engine.news_window import extract_news_dates, filter_news_frame_by_window

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

SESSION = requests.Session()

def _exclude_etf_etn(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "name" not in df.columns:
        return df
    mask = df["name"].astype(str).map(is_etf_or_etn_name)
    return df[~mask].copy()


def _to_int(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s or s in {"nan", "None", "-"}:
        return 0
    sign = -1 if ("-" in s or "하락" in s) else 1
    nums = re.findall(r"\d+", s.replace(",", ""))
    if not nums:
        return 0
    return sign * int("".join(nums))


def _to_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").strip()
    if not s or s in {"nan", "None", "-"}:
        return 0.0
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace("%", ""))
    return float(m.group(0)) if m else 0.0


def _normalize_news_text(text: str) -> str:
    t = str(text or "").strip().lower()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[^0-9a-zA-Z가-힣]", "", t)
    return t


def _clean_news_text(text: str, *, limit: int = 320) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _filter_news_to_target_date(df: pd.DataFrame, target_date: date) -> pd.DataFrame:
    return filter_news_frame_by_window(df, target_date=target_date, published_at_col="published_at").drop(columns=["published_at_dt"], errors="ignore")


def _latest_date_and_tickers(df: pd.DataFrame, date_col: str, ticker_col: str = "ticker") -> tuple[date | None, list[str]]:
    if df.empty or date_col not in df.columns or ticker_col not in df.columns:
        return None, []
    ts = pd.to_datetime(df[date_col], errors="coerce")
    if ts.isna().all():
        return None, []
    latest_ts = ts.max()
    latest_date = latest_ts.date()
    tickers = (
        df.loc[ts.dt.date == latest_date, ticker_col]
        .astype(str)
        .str.zfill(6)
        .drop_duplicates()
        .tolist()
    )
    return latest_date, tickers


def _request_text(url: str, *, encoding: str = "euc-kr", params: Dict | None = None) -> str:
    r = SESSION.get(
        url,
        params=params,
        timeout=15,
        headers={"User-Agent": USER_AGENT, "Referer": "https://finance.naver.com"},
    )
    r.raise_for_status()
    r.encoding = encoding
    return r.text


def _request_json(url: str, *, params: Dict | None = None) -> Dict:
    r = SESSION.get(
        url,
        params=params,
        timeout=15,
        headers={"User-Agent": USER_AGENT, "Referer": "https://finance.naver.com/sise/"},
    )
    r.raise_for_status()
    return r.json()


def collect_quote_summary() -> Dict:
    payload = _request_json("https://finance.naver.com/sise/quoteSummary.naver")
    message = payload.get("message") if isinstance(payload, dict) else {}
    result = message.get("result") if isinstance(message, dict) else {}
    return result if isinstance(result, dict) else {}


def collect_universe(limit_per_market: int, max_pages: int, delay: float) -> pd.DataFrame:
    rows: List[Dict] = []
    market_specs = [("KOSPI", 0), ("KOSDAQ", 1)]

    for market, sosok in market_specs:
        collected = 0
        for page in range(1, max_pages + 1):
            url = "https://finance.naver.com/sise/sise_market_sum.naver"
            html = _request_text(url, params={"sosok": sosok, "page": page}, encoding="euc-kr")
            soup = BeautifulSoup(html, "lxml")

            for tr in soup.select("table.type_2 tr"):
                a = tr.select_one("a.tltle")
                if not a:
                    continue
                href = a.get("href", "")
                m = re.search(r"code=(\d{6})", href)
                if not m:
                    continue
                tds = tr.find_all("td")
                if len(tds) < 11:
                    continue
                code = m.group(1)
                name = a.get_text(strip=True)
                market_cap_eok = _to_int(tds[6].get_text(strip=True))
                volume = _to_int(tds[9].get_text(strip=True))
                rows.append(
                    {
                        "ticker": code,
                        "name": name,
                        "market": market,
                        "market_cap_eok": market_cap_eok,
                        "raw_volume": volume,
                    }
                )
                collected += 1
                if collected >= limit_per_market:
                    break
            if collected >= limit_per_market:
                break
            time.sleep(delay)

    df = pd.DataFrame(rows).drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    df = _exclude_etf_etn(df).reset_index(drop=True)
    return df


def _parse_fchart_ohlcv(text: str) -> List[Dict]:
    payload = text.strip()
    payload = payload.replace("\r", " ").replace("\n", " ")
    data = ast.literal_eval(payload)
    if not data or len(data) <= 1:
        return []

    out: List[Dict] = []
    for row in data[1:]:
        if not row or len(row) < 6:
            continue
        date_raw = str(row[0])
        if not re.fullmatch(r"\d{8}", date_raw):
            continue
        trade_date = datetime.strptime(date_raw, "%Y%m%d").date().isoformat()
        o = _to_float(row[1])
        h = _to_float(row[2])
        l = _to_float(row[3])
        c = _to_float(row[4])
        v = _to_int(row[5])
        fr = _to_float(row[6]) if len(row) > 6 else 0.0
        out.append(
            {
                "date": trade_date,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
                "foreign_retention_rate": fr,
                "trading_value": int(c * v),
            }
        )
    return out


def collect_ohlcv(universe: pd.DataFrame, start_date: str, end_date: str, delay: float) -> pd.DataFrame:
    rows: List[Dict] = []
    for _, row in universe.iterrows():
        code = str(row["ticker"]).zfill(6)
        url = "https://fchart.stock.naver.com/siseJson.naver"
        params = {
            "symbol": code,
            "requestType": "1",
            "startTime": start_date,
            "endTime": end_date,
            "timeframe": "day",
        }
        try:
            text = _request_text(url, encoding="utf-8", params=params)
            items = _parse_fchart_ohlcv(text)
            for item in items:
                rows.append(
                    {
                        "date": item["date"],
                        "ticker": code,
                        "open": item["open"],
                        "high": item["high"],
                        "low": item["low"],
                        "close": item["close"],
                        "volume": item["volume"],
                        "trading_value": item["trading_value"],
                        "foreign_retention_rate": item["foreign_retention_rate"],
                    }
                )
        except Exception:
            continue
        time.sleep(delay)

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["date", "ticker"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    return df


def _fetch_article_summary(url: str) -> str:
    article_url = str(url or "").strip()
    if not article_url:
        return ""

    try:
        landing = SESSION.get(
            article_url,
            timeout=15,
            headers={"User-Agent": USER_AGENT, "Referer": "https://finance.naver.com"},
        )
        landing.raise_for_status()
        landing.encoding = "euc-kr"
        redirect_match = re.search(r"top\.location\.href=['\"]([^'\"]+)['\"]", landing.text)
        if redirect_match:
            article_url = urljoin(article_url, redirect_match.group(1))
    except Exception:
        return ""

    try:
        article = SESSION.get(
            article_url,
            timeout=15,
            headers={"User-Agent": USER_AGENT, "Referer": "https://finance.naver.com"},
        )
        article.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(article.text, "lxml")
    og_desc = soup.select_one('meta[property="og:description"]')
    if og_desc and og_desc.get("content"):
        return _clean_news_text(str(og_desc.get("content", "") or ""))

    description = soup.select_one('meta[name="description"]')
    if description and description.get("content"):
        return _clean_news_text(str(description.get("content", "") or ""))

    body = soup.select_one("#dic_area") or soup.select_one("#newsct_article")
    if body:
        return _clean_news_text(body.get_text(" ", strip=True), limit=400)
    return ""


def _enrich_news_summaries(df: pd.DataFrame, per_ticker: int, delay: float) -> pd.DataFrame:
    if df.empty or per_ticker <= 0:
        return df

    enriched = df.copy()
    if "summary" not in enriched.columns:
        enriched["summary"] = ""
    enriched["summary"] = enriched["summary"].fillna("").astype(str)
    enriched["published_at_dt"] = pd.to_datetime(enriched["published_at"], errors="coerce") if "published_at" in enriched.columns else pd.NaT
    enriched = enriched.sort_values(
        ["ticker", "relevance_score", "published_at_dt"],
        ascending=[True, False, False],
    )

    for _, group in enriched.groupby("ticker", sort=False):
        fetched = 0
        for idx, row in group.iterrows():
            if fetched >= per_ticker:
                break
            if str(row.get("summary", "")).strip():
                continue
            summary = _fetch_article_summary(str(row.get("url", "")))
            if not summary:
                continue
            enriched.at[idx, "summary"] = summary
            fetched += 1
            if delay > 0:
                time.sleep(min(delay, 0.12))

    return enriched.drop(columns=["published_at_dt"], errors="ignore")


def collect_news(
    universe: pd.DataFrame,
    top_tickers: int,
    delay: float,
    summary_top_per_ticker: int = 3,
    target_date: date | None = None,
    snapshot_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows: List[Dict] = []
    target = universe.copy()
    if snapshot_df is not None and not snapshot_df.empty and "ticker" in snapshot_df.columns:
        snap = snapshot_df.copy()
        snap["ticker"] = snap["ticker"].astype(str).str.zfill(6)
        if "change_pct" in snap.columns:
            snap["change_pct"] = pd.to_numeric(snap["change_pct"], errors="coerce").fillna(0.0)
        if "trading_value" in snap.columns:
            snap["trading_value"] = pd.to_numeric(snap["trading_value"], errors="coerce").fillna(0.0)
        snap = snap.sort_values(["change_pct", "trading_value"], ascending=[False, False])
        if top_tickers > 0:
            snap = snap.head(top_tickers)
        target = target.copy()
        target["ticker"] = target["ticker"].astype(str).str.zfill(6)
        order = pd.DataFrame({"ticker": snap["ticker"].tolist(), "news_rank": range(len(snap))})
        target = order.merge(target, on="ticker", how="inner").sort_values("news_rank").drop(columns=["news_rank"])
    elif top_tickers <= 0 or top_tickers >= len(universe):
        target = universe.copy()
    else:
        target = universe.sort_values("market_cap_eok", ascending=False).head(top_tickers)

    for _, row in target.iterrows():
        code = str(row["ticker"]).zfill(6)
        name = str(row.get("name", "")).strip()
        normalized_name = _normalize_news_text(name)
        url = "https://finance.naver.com/item/news_news.naver"
        params = {"code": code, "page": 1, "sm": "title_entity_id.basic"}
        try:
            html = _request_text(url, encoding="euc-kr", params=params)
        except Exception:
            continue
        soup = BeautifulSoup(html, "lxml")
        for tr in soup.select("table.type5 tr"):
            a = tr.select_one("a[href*='news_read']")
            if not a:
                continue
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            title = a.get_text(strip=True)
            source = tds[-2].get_text(strip=True)
            dt_text = tds[-1].get_text(strip=True)
            normalized_title = _normalize_news_text(title)
            exact_match = bool(normalized_name and normalized_name in normalized_title)
            relevance_score = 1.0 if exact_match else 0.35
            try:
                published_at = datetime.strptime(dt_text, "%Y.%m.%d %H:%M").isoformat()
            except ValueError:
                published_at = ""
            rows.append(
                {
                    "ticker": code,
                    "name": name,
                    "published_at": published_at,
                    "title": title,
                    "summary": "",
                    "source": source,
                    "url": urljoin("https://finance.naver.com", a.get("href", "")),
                    "relevance_score": relevance_score,
                    "is_fallback": 0 if exact_match else 1,
                }
            )
        time.sleep(delay)

    if not rows:
        return pd.DataFrame(
            columns=[
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
        )

    df = pd.DataFrame(rows).drop_duplicates(subset=["ticker", "title", "published_at"]).reset_index(drop=True)
    df["published_at_dt"] = pd.to_datetime(df["published_at"], errors="coerce")
    df = df.sort_values(
        ["ticker", "relevance_score", "published_at_dt"],
        ascending=[True, False, False],
    ).drop(columns=["published_at_dt"])
    df = _filter_news_to_target_date(df, target_date or date.today())
    df = _enrich_news_summaries(df, per_ticker=max(0, int(summary_top_per_ticker)), delay=delay)
    return df.reset_index(drop=True)


def _pick_flow_table(html: str) -> pd.DataFrame | None:
    tables = pd.read_html(StringIO(html), flavor="lxml")
    for t in tables:
        cols = [" ".join([str(x) for x in c if str(x) != "nan"]).strip() if isinstance(c, tuple) else str(c) for c in t.columns]
        joined = " | ".join(cols)
        if "날짜" in joined and "기관" in joined and "외국인" in joined:
            t = t.copy()
            t.columns = cols
            return t
    return None


def collect_flows(universe: pd.DataFrame, top_tickers: int, pages: int, delay: float) -> pd.DataFrame:
    rows: List[Dict] = []
    target = universe.sort_values("market_cap_eok", ascending=False).head(top_tickers)

    for _, row in target.iterrows():
        code = str(row["ticker"]).zfill(6)
        for page in range(1, pages + 1):
            url = "https://finance.naver.com/item/frgn.naver"
            params = {"code": code, "page": page}
            try:
                html = _request_text(url, encoding="euc-kr", params=params)
                table = _pick_flow_table(html)
                if table is None:
                    break
            except Exception:
                break

            date_col = next((c for c in table.columns if "날짜" in c), None)
            inst_col = next((c for c in table.columns if "기관" in c and "순매매량" in c), None)
            foreign_col = next((c for c in table.columns if "외국인" in c and "순매매량" in c), None)
            if not (date_col and inst_col and foreign_col):
                continue

            for _, r in table.iterrows():
                d = str(r.get(date_col, "")).strip()
                if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", d):
                    continue
                trade_date = datetime.strptime(d, "%Y.%m.%d").date().isoformat()
                inst = _to_int(r.get(inst_col))
                foreign = _to_int(r.get(foreign_col))
                rows.append(
                    {
                        "date": trade_date,
                        "ticker": code,
                        "foreign_net_buy": foreign,
                        "inst_net_buy": inst,
                        "retail_net_buy": -(foreign + inst),
                    }
                )
            time.sleep(delay)

    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "foreign_net_buy", "inst_net_buy", "retail_net_buy"])
    df = pd.DataFrame(rows).drop_duplicates(subset=["date", "ticker"]).sort_values(["ticker", "date"])
    return df.reset_index(drop=True)


def _parse_quote_summary_time(raw: str) -> tuple[str, str]:
    text = str(raw or "").strip()
    if len(text) >= 8 and text[:8].isdigit():
        trade_date = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    else:
        trade_date = date.today().isoformat()
    snapshot_time = ""
    try:
        ts = pd.to_datetime(text, format="%Y%m%d%H%M%S", errors="coerce")
        if pd.notna(ts):
            snapshot_time = ts.to_pydatetime().isoformat()
    except Exception:
        snapshot_time = ""
    return trade_date, snapshot_time


def collect_market_context(quote_summary: Dict) -> pd.DataFrame:
    rows: List[Dict] = []
    main_index_map = quote_summary.get("mainIndexMap") if isinstance(quote_summary, dict) else {}
    if not isinstance(main_index_map, dict):
        return pd.DataFrame()

    market_map = {
        "KOSPI": ("KOSPI", "코스피"),
        "KOSDAQ": ("KOSDAQ", "코스닥"),
    }
    for source_key, (market_key, market_label) in market_map.items():
        item = main_index_map.get(source_key)
        if not isinstance(item, dict):
            continue
        trade_date, snapshot_time = _parse_quote_summary_time(item.get("thistime"))
        rows.append(
            {
                "trade_date": trade_date,
                "market": market_key,
                "market_label": market_label,
                "market_status": str(item.get("marketStatus", "") or ""),
                "index_value": float(item.get("nowVal", 0) or 0) / 100.0,
                "change_pct": float(item.get("changeRate", 0) or 0),
                "rise_count": int(item.get("riseCnt", 0) or 0),
                "steady_count": int(item.get("steadyCnt", 0) or 0),
                "fall_count": int(item.get("fallCnt", 0) or 0),
                "upper_count": int(item.get("upperCnt", 0) or 0),
                "lower_count": int(item.get("lowerCnt", 0) or 0),
                "snapshot_time": snapshot_time,
            }
        )
    return pd.DataFrame(rows)


def _program_market_key(sosok: str) -> str:
    return {"01": "KOSPI", "02": "KOSDAQ"}.get(str(sosok or "").strip(), str(sosok or "").strip())


def collect_program_trend(quote_summary: Dict) -> pd.DataFrame:
    rows: List[Dict] = []
    market_keys = ["kospiTrendProgram", "kosdaqTrendProgram"]
    main_index_map = quote_summary.get("mainIndexMap") if isinstance(quote_summary, dict) else {}
    for key in market_keys:
        item = quote_summary.get(key)
        if not isinstance(item, dict):
            continue
        market = _program_market_key(item.get("sosok"))
        index_item = main_index_map.get(market) if isinstance(main_index_map, dict) else {}
        if not isinstance(index_item, dict):
            index_item = {}
        trade_date, snapshot_time = _parse_quote_summary_time(index_item.get("thistime") or item.get("bizdate"))
        arbitrage_buy = int(item.get("differenceBuyConsignAmount", 0) or 0) + int(item.get("differenceBuySelfAmount", 0) or 0)
        arbitrage_sell = int(item.get("differenceSellConsignAmount", 0) or 0) + int(item.get("differenceSellSelfAmount", 0) or 0)
        non_arbitrage_buy = int(item.get("biDifferenceBuyConsignAmount", 0) or 0) + int(item.get("biDifferenceBuySelfAmount", 0) or 0)
        non_arbitrage_sell = int(item.get("biDifferenceSellConsignAmount", 0) or 0) + int(item.get("biDifferenceSellSelfAmount", 0) or 0)
        total_buy = arbitrage_buy + non_arbitrage_buy
        total_sell = arbitrage_sell + non_arbitrage_sell
        rows.append(
            {
                "trade_date": trade_date,
                "market": market,
                "market_status": str(index_item.get("marketStatus", "") or ""),
                "arbitrage_buy": arbitrage_buy,
                "arbitrage_sell": arbitrage_sell,
                "arbitrage_net": arbitrage_buy - arbitrage_sell,
                "non_arbitrage_buy": non_arbitrage_buy,
                "non_arbitrage_sell": non_arbitrage_sell,
                "non_arbitrage_net": non_arbitrage_buy - non_arbitrage_sell,
                "total_buy": total_buy,
                "total_sell": total_sell,
                "total_net": total_buy - total_sell,
                "snapshot_time": snapshot_time,
            }
        )
    return pd.DataFrame(rows)


def build_latest_snapshot(universe: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
    if ohlcv.empty:
        return pd.DataFrame()
    tmp = ohlcv.sort_values(["ticker", "date"]).copy()
    tmp["prev_close"] = tmp.groupby("ticker")["close"].shift(1)
    latest = tmp.groupby("ticker", as_index=False).tail(1).copy()
    latest["change_pct"] = (
        (latest["close"] - latest["prev_close"]) / latest["prev_close"].replace(0, pd.NA) * 100
    ).fillna(0.0)
    latest["change_pct"] = latest["change_pct"].round(2)
    merged = latest.merge(
        universe[["ticker", "name", "market", "market_cap_eok"]],
        on="ticker",
        how="inner",
    )
    merged = _exclude_etf_etn(merged)
    merged = merged[
        [
            "date",
            "ticker",
            "name",
            "market",
            "close",
            "change_pct",
            "volume",
            "trading_value",
            "market_cap_eok",
        ]
    ]
    return merged.sort_values("change_pct", ascending=False).reset_index(drop=True)


def _parse_steps(raw: str) -> List[str]:
    valid = {"universe", "ohlcv", "flows", "news", "snapshot", "market", "program"}
    text = str(raw or "all").strip().lower()
    if text in {"all", "*"}:
        return ["universe", "ohlcv", "flows", "news", "snapshot", "market", "program"]
    steps = [s.strip() for s in text.split(",") if s.strip()]
    for s in steps:
        if s not in valid:
            raise ValueError(f"Invalid step: {s}. valid={sorted(valid)}")
    # keep user order, remove duplicates
    seen = set()
    out: List[str] = []
    for s in steps:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _load_existing_csv(path: Path, name: str, repo: SupabaseRepository | None = None) -> pd.DataFrame:
    if repo is None:
        raise RuntimeError(f"DB backend required for step '{name}'")
    loader_map = {
        "universe": repo.load_universe_df,
        "ohlcv": repo.load_ohlcv_df,
        "flows": repo.load_flows_df,
        "news": repo.load_news_df,
        "snapshot": repo.load_snapshot_df,
        "market": repo.load_market_context_df,
        "program": repo.load_program_trend_df,
    }
    loader = loader_map.get(name)
    if loader is None:
        raise RuntimeError(f"Unknown loader for step '{name}'")
    df = loader()
    if df.empty:
        raise RuntimeError(f"Missing required DB data for step '{name}'")
    if name == "universe":
        df = _exclude_etf_etn(df)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Naver bootstrap collector for closing-bet system")
    parser.add_argument("--data-dir", default="data/naver")
    parser.add_argument("--limit-per-market", type=int, default=120)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--flow-pages", type=int, default=3)
    parser.add_argument("--news-top", type=int, default=30)
    parser.add_argument("--news-summary-top", type=int, default=3)
    parser.add_argument("--flow-top", type=int, default=120)
    parser.add_argument("--delay", type=float, default=0.08)
    parser.add_argument(
        "--refresh-today",
        default=os.getenv("BATCH_REFRESH_TODAY", "1"),
        help="1/true to replace today's rows for fetched tickers before upsert",
    )
    parser.add_argument(
        "--steps",
        default="all",
        help="comma separated: universe,ohlcv,flows,news,snapshot or all",
    )
    args = parser.parse_args()

    out_dir = Path(args.data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not is_supabase_backend():
        raise SystemExit("DB backend is required. Set STORAGE_BACKEND=supabase and SUPABASE_DATABASE_URL")
    repo = SupabaseRepository.from_env()
    export_files = str(os.getenv("EXPORT_LOCAL_FILES", "0")).strip() in {"1", "true", "TRUE"}
    refresh_today = str(args.refresh_today).strip().lower() in {"1", "true", "yes", "y", "on"}

    steps = _parse_steps(args.steps)
    print(f"Running steps: {', '.join(steps)}")

    universe_path = out_dir / "universe.csv"
    ohlcv_path = out_dir / "ohlcv_1d.csv"
    flows_path = out_dir / "flows_1d.csv"
    news_path = out_dir / "news_items.csv"
    snapshot_path = out_dir / "latest_snapshot.csv"
    market_context_path = out_dir / "market_context.csv"
    program_trend_path = out_dir / "program_trend.csv"

    universe: pd.DataFrame | None = None
    ohlcv: pd.DataFrame | None = None
    snap: pd.DataFrame | None = None
    quote_summary: Dict | None = None

    if "universe" in steps:
        print("[step] universe collecting...")
        universe = collect_universe(args.limit_per_market, args.max_pages, args.delay)
        repo.upsert_universe(universe)
        if export_files:
            universe.to_csv(universe_path, index=False, encoding="utf-8-sig")
        print(f"  universe rows: {len(universe)}")
    elif any(s in steps for s in ["ohlcv", "flows", "news", "snapshot"]):
        try:
            universe = _load_existing_csv(universe_path, "universe", repo=repo)
        except Exception:
            print("[step] universe missing in DB, collecting fallback...")
            universe = collect_universe(args.limit_per_market, args.max_pages, args.delay)
            repo.upsert_universe(universe)
            if export_files:
                universe.to_csv(universe_path, index=False, encoding="utf-8-sig")
            print(f"  universe rows: {len(universe)}")

    if "ohlcv" in steps:
        assert universe is not None
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=args.days * 2)
        print("[step] ohlcv collecting...")
        ohlcv = collect_ohlcv(
            universe,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            delay=args.delay,
        )
        if refresh_today and not ohlcv.empty:
            latest_date, latest_tickers = _latest_date_and_tickers(ohlcv, "date")
            if latest_date and latest_tickers:
                deleted = repo.delete_trade_dates("naver_ohlcv_1d", [latest_date], tickers=latest_tickers)
                if deleted:
                    print(f"  ohlcv refresh delete(latest={latest_date.isoformat()}): {deleted}")
        repo.upsert_ohlcv(ohlcv)
        if export_files:
            ohlcv.to_csv(ohlcv_path, index=False, encoding="utf-8-sig")
        print(f"  ohlcv rows: {len(ohlcv)}")
    elif "snapshot" in steps:
        ohlcv = _load_existing_csv(ohlcv_path, "ohlcv", repo=repo)

    if "flows" in steps:
        assert universe is not None
        print("[step] flows collecting...")
        flows = collect_flows(universe, args.flow_top, args.flow_pages, args.delay)
        if refresh_today and not flows.empty:
            latest_date, latest_tickers = _latest_date_and_tickers(flows, "date")
            if latest_date and latest_tickers:
                deleted = repo.delete_trade_dates("naver_flows_1d", [latest_date], tickers=latest_tickers)
                if deleted:
                    print(f"  flows refresh delete(latest={latest_date.isoformat()}): {deleted}")
        repo.upsert_flows(flows)
        if export_files:
            flows.to_csv(flows_path, index=False, encoding="utf-8-sig")
        print(f"  flows rows: {len(flows)}")

    if "news" in steps:
        assert universe is not None
        print("[step] news collecting...")
        snapshot_for_news = snap
        if snapshot_for_news is None or snapshot_for_news.empty:
            try:
                snapshot_for_news = _load_existing_csv(snapshot_path, "snapshot", repo=repo)
            except Exception:
                snapshot_for_news = None
        if (snapshot_for_news is None or snapshot_for_news.empty) and universe is not None and ohlcv is not None and not ohlcv.empty:
            snapshot_for_news = build_latest_snapshot(universe, ohlcv)
        news = collect_news(
            universe,
            args.news_top,
            args.delay,
            summary_top_per_ticker=args.news_summary_top,
            target_date=date.today(),
            snapshot_df=snapshot_for_news,
        )
        if refresh_today and not news.empty and "published_at" in news.columns:
            news_dates = extract_news_dates(news, published_at_col="published_at")
            latest_tickers = news["ticker"].astype(str).str.zfill(6).drop_duplicates().tolist() if "ticker" in news.columns else []
            if news_dates and latest_tickers:
                deleted = repo.delete_news_dates(news_dates, tickers=latest_tickers)
                if deleted:
                    date_text = ",".join(d.isoformat() for d in news_dates)
                    print(f"  news refresh delete(dates={date_text}): {deleted}")
        repo.upsert_news(news)
        if export_files:
            news.to_csv(news_path, index=False, encoding="utf-8-sig")
        print(f"  news rows: {len(news)}")

    if "snapshot" in steps:
        assert universe is not None
        assert ohlcv is not None
        print("[step] latest snapshot building...")
        snap = build_latest_snapshot(universe, ohlcv)
        if refresh_today and not snap.empty:
            latest_date, latest_tickers = _latest_date_and_tickers(snap, "date")
            if latest_date and latest_tickers:
                deleted = repo.delete_trade_dates("naver_latest_snapshot", [latest_date], tickers=latest_tickers)
                if deleted:
                    print(f"  snapshot refresh delete(latest={latest_date.isoformat()}): {deleted}")
        repo.upsert_snapshot(snap)
        if export_files:
            snap.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
        print(f"  snapshot rows: {len(snap)}")

    if "market" in steps or "program" in steps:
        quote_summary = collect_quote_summary()

    if "market" in steps:
        print("[step] market context collecting...")
        market_context = collect_market_context(quote_summary or {})
        repo.upsert_market_context(market_context)
        if export_files:
            market_context.to_csv(market_context_path, index=False, encoding="utf-8-sig")
        print(f"  market rows: {len(market_context)}")

    if "program" in steps:
        print("[step] program trend collecting...")
        program_trend = collect_program_trend(quote_summary or {})
        repo.upsert_program_trend(program_trend)
        if export_files:
            program_trend.to_csv(program_trend_path, index=False, encoding="utf-8-sig")
        print(f"  program rows: {len(program_trend)}")

    print("\nDone.")
    print(f"Output: {out_dir.resolve()}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from supabase_py.db import is_supabase_backend
from supabase_py.repository import SupabaseRepository

from engine.config import SignalConfig
from engine.krx_filters import is_etf_or_etn_name
from engine.news_window import build_news_window, describe_news_window, normalize_published_at_series
from engine.models import (
    ChartData,
    IntradayFeatureData,
    MarketContextData,
    NewsItem,
    ProgramTradeData,
    StockData,
    SupplyData,
)


def _stable_seed(*parts: str) -> int:
    raw = "|".join(parts)
    return sum((i + 1) * ord(ch) for i, ch in enumerate(raw))


def _normalize_news_text(text: str) -> str:
    value = str(text or "").strip().lower()
    value = " ".join(value.split())
    return "".join(ch for ch in value if ch.isalnum() or ("가" <= ch <= "힣"))


def _normalize_ticker(value: object) -> str:
    return str(value or "").strip().zfill(6)


@dataclass
class _UniverseRow:
    code: str
    name: str
    market: str
    sector: str


class KRXCollector:
    """
    Collector with priority:
    1) DB datasets (Supabase/Postgres)
    2) Synthetic fallback data (for empty state / smoke tests)
    """

    def __init__(self, config: SignalConfig):
        self.config = config
        self.allow_synthetic_market_fallback = bool(
            getattr(config, "allow_synthetic_market_data_fallback", False)
        )
        self._universe = self._default_universe()

        self.repo: Optional[SupabaseRepository] = None
        if is_supabase_backend():
            try:
                self.repo = SupabaseRepository.from_env()
            except Exception:
                self.repo = None

        self.universe_df = self._read_csv("universe.csv")
        self.ohlcv_df = self._read_csv("ohlcv_1d.csv")
        self.flows_df = self._read_csv("flows_1d.csv")
        self.snapshot_df = self._read_csv("latest_snapshot.csv")
        self.market_context_df = self._read_csv("market_context.csv")
        self.program_trend_df = self._read_csv("program_trend.csv")
        self.intraday_df = self._read_csv("kiwoom_intraday_features.csv")
        self.intraday_snapshots_df = self._read_csv("kiwoom_intraday_snapshots.csv")
        self.condition_hits_df = self._read_csv("kiwoom_condition_hits.csv")
        self.program_snapshots_df = self._read_csv("kiwoom_program_snapshots.csv")

        self._real_mode = (
            self.universe_df is not None
            and not self.universe_df.empty
            and self.ohlcv_df is not None
            and not self.ohlcv_df.empty
        )

        if self._real_mode and (self.snapshot_df is None or self.snapshot_df.empty):
            self.snapshot_df = self._build_snapshot_from_ohlcv()

        self._snapshot_by_market: Dict[str, pd.DataFrame] = {}
        self._snapshot_by_ticker: Dict[str, pd.Series] = {}
        self._ohlcv_by_ticker: Dict[str, pd.DataFrame] = {}
        self._flows_by_ticker: Dict[str, pd.DataFrame] = {}
        self._market_context_by_market: Dict[str, pd.Series] = {}
        self._program_by_market: Dict[str, pd.Series] = {}
        self._intraday_by_ticker: Dict[str, pd.Series] = {}
        self._prepare_indexes()

    async def __aenter__(self) -> "KRXCollector":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def _prepare_indexes(self) -> None:
        if self.snapshot_df is not None and not self.snapshot_df.empty:
            df = self.snapshot_df.copy()
            if "ticker" in df.columns:
                df["ticker_norm"] = df["ticker"].map(_normalize_ticker)
            if "market" in df.columns:
                df["market_norm"] = df["market"].astype(str).str.upper()
            if "change_pct" in df.columns:
                df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0.0)
            if "name" in df.columns:
                df = df[~df["name"].astype(str).map(is_etf_or_etn_name)]
            self.snapshot_df = df.reset_index(drop=True)
            if "market_norm" in self.snapshot_df.columns:
                for market_key, group in self.snapshot_df.groupby("market_norm", sort=False):
                    self._snapshot_by_market[str(market_key)] = group.sort_values("change_pct", ascending=False).reset_index(drop=True)
            if "ticker_norm" in self.snapshot_df.columns:
                dedup = self.snapshot_df.drop_duplicates(subset=["ticker_norm"], keep="last")
                self._snapshot_by_ticker = {str(row["ticker_norm"]): row for _, row in dedup.iterrows()}

        if self.ohlcv_df is not None and not self.ohlcv_df.empty:
            df = self.ohlcv_df.copy()
            if "ticker" in df.columns:
                df["ticker_norm"] = df["ticker"].map(_normalize_ticker)
            if "date" in df.columns:
                df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
                df = df.sort_values(["ticker_norm", "date_dt"])
            self.ohlcv_df = df.reset_index(drop=True)
            if "ticker_norm" in self.ohlcv_df.columns:
                self._ohlcv_by_ticker = {
                    str(ticker): group.reset_index(drop=True)
                    for ticker, group in self.ohlcv_df.groupby("ticker_norm", sort=False)
                }

        if self.flows_df is not None and not self.flows_df.empty:
            df = self.flows_df.copy()
            if "ticker" in df.columns:
                df["ticker_norm"] = df["ticker"].map(_normalize_ticker)
            if "date" in df.columns:
                df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
                df = df.sort_values(["ticker_norm", "date_dt"])
            self.flows_df = df.reset_index(drop=True)
            if "ticker_norm" in self.flows_df.columns:
                self._flows_by_ticker = {
                    str(ticker): group.reset_index(drop=True)
                    for ticker, group in self.flows_df.groupby("ticker_norm", sort=False)
                }

        if self.market_context_df is not None and not self.market_context_df.empty:
            df = self.market_context_df.copy()
            if "market" in df.columns:
                df["market_norm"] = df["market"].astype(str).str.upper()
            if "trade_date" in df.columns:
                df["trade_date_dt"] = pd.to_datetime(df["trade_date"], errors="coerce")
                df = df.sort_values(["market_norm", "trade_date_dt"])
            self.market_context_df = df.reset_index(drop=True)
            if "market_norm" in self.market_context_df.columns:
                dedup = self.market_context_df.drop_duplicates(subset=["market_norm"], keep="last")
                self._market_context_by_market = {str(row["market_norm"]): row for _, row in dedup.iterrows()}

        if self.program_trend_df is not None and not self.program_trend_df.empty:
            df = self.program_trend_df.copy()
            if "market" in df.columns:
                df["market_norm"] = df["market"].astype(str).str.upper()
            if "trade_date" in df.columns:
                df["trade_date_dt"] = pd.to_datetime(df["trade_date"], errors="coerce")
                df = df.sort_values(["market_norm", "trade_date_dt"])
            self.program_trend_df = df.reset_index(drop=True)
            if "market_norm" in self.program_trend_df.columns:
                dedup = self.program_trend_df.drop_duplicates(subset=["market_norm"], keep="last")
                self._program_by_market = {str(row["market_norm"]): row for _, row in dedup.iterrows()}

        if self.intraday_df is not None and not self.intraday_df.empty:
            df = self.intraday_df.copy()
            if "ticker" in df.columns:
                df["ticker_norm"] = df["ticker"].map(_normalize_ticker)
            self.intraday_df = df.reset_index(drop=True)
            if "ticker_norm" in self.intraday_df.columns:
                dedup = self.intraday_df.drop_duplicates(subset=["ticker_norm"], keep="last")
                self._intraday_by_ticker = {str(row["ticker_norm"]): row for _, row in dedup.iterrows()}

    async def get_top_gainers(self, market: str, top_n: int) -> List[StockData]:
        market_key = str(market or "").strip().upper()
        if self._real_mode and self._snapshot_by_market:
            df = self._snapshot_by_market.get(market_key, pd.DataFrame()).head(top_n)
            rows: List[StockData] = []
            for _, r in df.iterrows():
                rows.append(
                    StockData(
                        code=str(r.get("ticker", "")).zfill(6),
                        name=str(r.get("name", "")),
                        market=str(r.get("market", market)),
                        sector=str(r.get("sector", "")),
                        close=float(r.get("close", 0) or 0),
                        change_pct=float(r.get("change_pct", 0) or 0),
                        trading_value=int(float(r.get("trading_value", 0) or 0)),
                        volume=int(float(r.get("volume", 0) or 0)),
                        marcap=int(float(r.get("market_cap_eok", 0) or 0) * 100_000_000),
                        high_52w=float(r.get("high_52w", 0) or 0),
                    )
                )
            if rows:
                return rows

        if self.allow_synthetic_market_fallback:
            return self._synthetic_top_gainers(market, top_n)
        return []

    async def get_stock_detail(self, code: str) -> Optional[StockData]:
        code = str(code).zfill(6)
        if self._real_mode and self._snapshot_by_ticker:
            r = self._snapshot_by_ticker.get(code)
            if r is not None:
                if is_etf_or_etn_name(str(r.get("name", ""))):
                    return None
                high_52w = 0.0
                s = self._ohlcv_by_ticker.get(code)
                if s is not None and not s.empty:
                    high_52w = float(s["high"].max())
                return StockData(
                    code=code,
                    name=str(r.get("name", "")),
                    market=str(r.get("market", "")),
                    sector=str(r.get("sector", "")),
                    close=float(r.get("close", 0) or 0),
                    change_pct=float(r.get("change_pct", 0) or 0),
                    trading_value=int(float(r.get("trading_value", 0) or 0)),
                    volume=int(float(r.get("volume", 0) or 0)),
                    marcap=int(float(r.get("market_cap_eok", 0) or 0) * 100_000_000),
                    high_52w=high_52w,
                )

        if self.allow_synthetic_market_fallback:
            return self._synthetic_stock_detail(code)
        return None

    async def get_chart_data(self, code: str, days: int = 60) -> List[ChartData]:
        code = str(code).zfill(6)
        if self._real_mode and self._ohlcv_by_ticker:
            s = self._ohlcv_by_ticker.get(code)
            if s is not None and not s.empty:
                s = s.tail(days)
                out: List[ChartData] = []
                for _, r in s.iterrows():
                    out.append(
                        ChartData(
                            trade_date=pd.to_datetime(r["date"]).date(),
                            open=float(r.get("open", 0) or 0),
                            high=float(r.get("high", 0) or 0),
                            low=float(r.get("low", 0) or 0),
                            close=float(r.get("close", 0) or 0),
                            volume=int(float(r.get("volume", 0) or 0)),
                        )
                    )
                if out:
                    return out

        if self.allow_synthetic_market_fallback:
            return self._synthetic_chart_data(code, days)
        return []

    async def get_supply_data(self, code: str) -> SupplyData:
        code = str(code).zfill(6)
        if self._flows_by_ticker:
            s = self._flows_by_ticker.get(code)
            if s is not None and not s.empty:
                s = s.tail(5)
                return SupplyData(
                    foreign_buy_5d=int(s.get("foreign_net_buy", pd.Series(dtype=float)).fillna(0).sum()),
                    inst_buy_5d=int(s.get("inst_net_buy", pd.Series(dtype=float)).fillna(0).sum()),
                    individual_buy_5d=int(s.get("retail_net_buy", pd.Series(dtype=float)).fillna(0).sum()),
                )

        if self.allow_synthetic_market_fallback:
            return self._synthetic_supply(code)
        return SupplyData()

    async def get_market_context(self, market: str) -> MarketContextData:
        market = str(market or "").strip().upper()
        row = self._market_context_by_market.get(market)
        if row is not None:
                trade_date = None
                snapshot_time = None
                if str(row.get("trade_date", "")).strip():
                    try:
                        trade_date = pd.to_datetime(row["trade_date"]).date()
                    except Exception:
                        trade_date = None
                if str(row.get("snapshot_time", "")).strip():
                    try:
                        snapshot_time = pd.to_datetime(row["snapshot_time"]).to_pydatetime()
                    except Exception:
                        snapshot_time = None
                return MarketContextData(
                    market=market,
                    market_label=str(row.get("market_label", market)),
                    trade_date=trade_date,
                    snapshot_time=snapshot_time,
                    market_status=str(row.get("market_status", "")),
                    index_value=float(row.get("index_value", 0) or 0),
                    change_pct=float(row.get("change_pct", 0) or 0),
                    rise_count=int(float(row.get("rise_count", 0) or 0)),
                    steady_count=int(float(row.get("steady_count", 0) or 0)),
                    fall_count=int(float(row.get("fall_count", 0) or 0)),
                    upper_count=int(float(row.get("upper_count", 0) or 0)),
                    lower_count=int(float(row.get("lower_count", 0) or 0)),
                )
        return MarketContextData(market=market, market_label=market)

    async def get_program_trade(self, market: str) -> ProgramTradeData:
        market = str(market or "").strip().upper()
        row = self._program_by_market.get(market)
        if row is not None:
                trade_date = None
                snapshot_time = None
                if str(row.get("trade_date", "")).strip():
                    try:
                        trade_date = pd.to_datetime(row["trade_date"]).date()
                    except Exception:
                        trade_date = None
                if str(row.get("snapshot_time", "")).strip():
                    try:
                        snapshot_time = pd.to_datetime(row["snapshot_time"]).to_pydatetime()
                    except Exception:
                        snapshot_time = None
                return ProgramTradeData(
                    market=market,
                    trade_date=trade_date,
                    snapshot_time=snapshot_time,
                    market_status=str(row.get("market_status", "")),
                    arbitrage_buy=int(float(row.get("arbitrage_buy", 0) or 0)),
                    arbitrage_sell=int(float(row.get("arbitrage_sell", 0) or 0)),
                    arbitrage_net=int(float(row.get("arbitrage_net", 0) or 0)),
                    non_arbitrage_buy=int(float(row.get("non_arbitrage_buy", 0) or 0)),
                    non_arbitrage_sell=int(float(row.get("non_arbitrage_sell", 0) or 0)),
                    non_arbitrage_net=int(float(row.get("non_arbitrage_net", 0) or 0)),
                    total_buy=int(float(row.get("total_buy", 0) or 0)),
                    total_sell=int(float(row.get("total_sell", 0) or 0)),
                    total_net=int(float(row.get("total_net", 0) or 0)),
                )
        return ProgramTradeData(market=market)

    async def get_intraday_feature(self, code: str) -> IntradayFeatureData:
        ticker = str(code or "").zfill(6)
        row = self._intraday_by_ticker.get(ticker)
        if row is not None:
                raw_names = row.get("condition_names")
                if isinstance(raw_names, list):
                    condition_names = [str(v) for v in raw_names if str(v).strip()]
                else:
                    condition_names = []
                return IntradayFeatureData(
                    ticker=ticker,
                    venue=str(row.get("venue", "")),
                    current_price=float(row.get("current_price", 0) or 0),
                    change_pct=float(row.get("change_pct", 0) or 0),
                    bid_total=int(float(row.get("bid_total", 0) or 0)),
                    ask_total=int(float(row.get("ask_total", 0) or 0)),
                    orderbook_imbalance=float(row.get("orderbook_imbalance", 0) or 0),
                    execution_strength=float(row.get("execution_strength", 0) or 0),
                    tick_volume=int(float(row.get("tick_volume", 0) or 0)),
                    minute_pattern=str(row.get("minute_pattern", "")),
                    minute_breakout_score=float(row.get("minute_breakout_score", 0) or 0),
                    volume_surge_ratio=float(row.get("volume_surge_ratio", 0) or 0),
                    orderbook_surge_ratio=float(row.get("orderbook_surge_ratio", 0) or 0),
                    vi_active=bool(row.get("vi_active", False)),
                    vi_type=str(row.get("vi_type", "")),
                    condition_hit_count=int(float(row.get("condition_hit_count", 0) or 0)),
                    condition_names=condition_names,
                    acc_trade_value=int(float(row.get("acc_trade_value", 0) or 0)),
                    acc_trade_volume=int(float(row.get("acc_trade_volume", 0) or 0)),
                )
        return IntradayFeatureData(ticker=ticker)

    def _read_csv(self, name: str) -> Optional[pd.DataFrame]:
        if self.repo is None:
            return None
        try:
            loader = {
                "universe.csv": self.repo.load_universe_df,
                "ohlcv_1d.csv": self.repo.load_ohlcv_df,
                "flows_1d.csv": self.repo.load_flows_df,
                "latest_snapshot.csv": self.repo.load_snapshot_df,
                "market_context.csv": self.repo.load_market_context_df,
                "program_trend.csv": self.repo.load_program_trend_df,
                "kiwoom_intraday_features.csv": self.repo.load_kiwoom_intraday_df,
                "kiwoom_intraday_snapshots.csv": self.repo.load_kiwoom_intraday_snapshot_df,
                "kiwoom_condition_hits.csv": self.repo.load_kiwoom_condition_hits_df,
                "kiwoom_program_snapshots.csv": self.repo.load_kiwoom_program_snapshot_df,
            }.get(name)
            if loader is None:
                return None
            df = loader()
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
            return None
        except Exception:
            return None

    def _build_snapshot_from_ohlcv(self) -> pd.DataFrame:
        assert self.ohlcv_df is not None
        tmp = self.ohlcv_df.copy()
        tmp["date"] = pd.to_datetime(tmp["date"])
        tmp = tmp.sort_values(["ticker", "date"])
        tmp["prev_close"] = tmp.groupby("ticker")["close"].shift(1)
        latest = tmp.groupby("ticker", as_index=False).tail(1).copy()
        latest["change_pct"] = (
            (latest["close"] - latest["prev_close"]) / latest["prev_close"].replace(0, pd.NA) * 100
        ).fillna(0.0)

        if self.universe_df is not None and not self.universe_df.empty:
            merged = latest.merge(self.universe_df, on="ticker", how="inner")
        else:
            merged = latest
        if "name" in merged.columns:
            merged = merged[~merged["name"].astype(str).map(is_etf_or_etn_name)]
        return merged

    # ===== synthetic fallback =====
    def _synthetic_top_gainers(self, market: str, top_n: int) -> List[StockData]:
        today = date.today().isoformat()
        rows = [r for r in self._universe if r.market == market]
        output: List[StockData] = []
        for r in rows:
            rng = random.Random(_stable_seed(today, market, r.code))
            close = float(rng.randrange(5_000, 250_000, 10))
            output.append(
                StockData(
                    code=r.code,
                    name=r.name,
                    market=r.market,
                    sector=r.sector,
                    close=close,
                    change_pct=round(rng.uniform(4.0, 22.0), 2),
                    trading_value=int(rng.uniform(80_000_000_000, 1_500_000_000_000)),
                    volume=int(rng.uniform(300_000, 30_000_000)),
                    marcap=int(rng.uniform(300_000_000_000, 250_000_000_000_000)),
                    high_52w=round(close * rng.uniform(1.0, 1.15), 2),
                )
            )
        output.sort(key=lambda x: x.change_pct, reverse=True)
        return output[:top_n]

    def _synthetic_stock_detail(self, code: str) -> Optional[StockData]:
        row = next((r for r in self._universe if r.code == code), None)
        if not row:
            return None
        rng = random.Random(_stable_seed("detail", code, date.today().isoformat()))
        close = float(rng.randrange(5_000, 250_000, 10))
        return StockData(
            code=row.code,
            name=row.name,
            market=row.market,
            sector=row.sector,
            close=close,
            change_pct=round(rng.uniform(3.0, 20.0), 2),
            trading_value=int(rng.uniform(80_000_000_000, 1_500_000_000_000)),
            volume=int(rng.uniform(300_000, 30_000_000)),
            marcap=int(rng.uniform(300_000_000_000, 250_000_000_000_000)),
            high_52w=round(close * rng.uniform(1.05, 1.2), 2),
        )

    def _synthetic_chart_data(self, code: str, days: int) -> List[ChartData]:
        today = date.today()
        rng = random.Random(_stable_seed("chart", code, today.isoformat()))
        base = float(rng.randrange(8_000, 180_000, 10))
        records: List[ChartData] = []
        prev_close = base * 0.9
        for i in range(days):
            d = today - timedelta(days=days - i)
            trend = 1.0 + i * 0.0015
            noise = rng.uniform(-0.015, 0.015)
            close = max(100.0, prev_close * trend * (1.0 + noise))
            open_ = prev_close * (1.0 + rng.uniform(-0.01, 0.01))
            high = max(close, open_) * (1.0 + rng.uniform(0.002, 0.03))
            low = min(close, open_) * (1.0 - rng.uniform(0.002, 0.02))
            volume = int(rng.uniform(200_000, 20_000_000))
            records.append(
                ChartData(
                    trade_date=d,
                    open=round(open_, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(close, 2),
                    volume=volume,
                )
            )
            prev_close = close
        return records

    def _synthetic_supply(self, code: str) -> SupplyData:
        rng = random.Random(_stable_seed("supply", code, date.today().isoformat()))
        return SupplyData(
            foreign_buy_5d=int(rng.uniform(-5_000_000_000, 12_000_000_000)),
            inst_buy_5d=int(rng.uniform(-3_000_000_000, 10_000_000_000)),
            individual_buy_5d=int(rng.uniform(-6_000_000_000, 6_000_000_000)),
        )

    @staticmethod
    def _default_universe() -> List[_UniverseRow]:
        return [
            _UniverseRow("005930", "삼성전자", "KOSPI", "반도체"),
            _UniverseRow("000660", "SK하이닉스", "KOSPI", "반도체"),
            _UniverseRow("035420", "NAVER", "KOSPI", "인터넷"),
            _UniverseRow("035720", "카카오", "KOSPI", "인터넷"),
            _UniverseRow("005380", "현대차", "KOSPI", "자동차"),
            _UniverseRow("012330", "현대모비스", "KOSPI", "자동차"),
            _UniverseRow("068270", "셀트리온", "KOSPI", "바이오"),
            _UniverseRow("207940", "삼성바이오로직스", "KOSPI", "바이오"),
            _UniverseRow("373220", "LG에너지솔루션", "KOSPI", "2차전지"),
            _UniverseRow("003670", "포스코퓨처엠", "KOSPI", "2차전지"),
            _UniverseRow("105560", "KB금융", "KOSPI", "금융"),
            _UniverseRow("055550", "신한지주", "KOSPI", "금융"),
            _UniverseRow("066570", "LG전자", "KOSPI", "전자"),
            _UniverseRow("033780", "KT&G", "KOSPI", "소비재"),
            _UniverseRow("017670", "SK텔레콤", "KOSPI", "통신"),
            _UniverseRow("091990", "셀트리온헬스케어", "KOSDAQ", "바이오"),
            _UniverseRow("247540", "에코프로비엠", "KOSDAQ", "2차전지"),
            _UniverseRow("086520", "에코프로", "KOSDAQ", "2차전지"),
            _UniverseRow("263750", "펄어비스", "KOSDAQ", "게임"),
            _UniverseRow("293490", "카카오게임즈", "KOSDAQ", "게임"),
            _UniverseRow("357780", "솔브레인", "KOSDAQ", "반도체소재"),
            _UniverseRow("240810", "원익IPS", "KOSDAQ", "반도체장비"),
            _UniverseRow("036570", "엔씨소프트", "KOSDAQ", "게임"),
            _UniverseRow("095660", "네오위즈", "KOSDAQ", "게임"),
            _UniverseRow("214150", "클래시스", "KOSDAQ", "의료기기"),
            _UniverseRow("298020", "효성티앤씨", "KOSDAQ", "소재"),
        ]


class EnhancedNewsCollector:
    def __init__(self, config: SignalConfig):
        self.config = config
        self.repo: Optional[SupabaseRepository] = None
        if is_supabase_backend():
            try:
                self.repo = SupabaseRepository.from_env()
            except Exception:
                self.repo = None
        self.news_df = self._read_news_csv()
        self._news_by_ticker: Dict[str, pd.DataFrame] = {}
        self._prepare_news_index()
        # 운영 기본값: synthetic 뉴스 fallback 비활성화
        self.allow_synthetic_fallback = bool(
            getattr(config, "allow_synthetic_news_fallback", False)
        )

    async def __aenter__(self) -> "EnhancedNewsCollector":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def _window_kwargs(self) -> Dict[str, int]:
        return {
            "cutoff_hour": int(getattr(self.config, "news_prev_day_cutoff_hour", 15) or 15),
            "cutoff_minute": int(getattr(self.config, "news_prev_day_cutoff_minute", 30) or 30),
        }

    def _prepare_news_index(self) -> None:
        if self.news_df is None or self.news_df.empty:
            return

        df = self.news_df.copy()
        if "ticker" in df.columns:
            df["ticker_norm"] = df["ticker"].map(_normalize_ticker)
        if "relevance_score" in df.columns:
            df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce").fillna(0.0)
        else:
            df["relevance_score"] = 0.0
        if "is_fallback" in df.columns:
            df["is_fallback"] = pd.to_numeric(df["is_fallback"], errors="coerce").fillna(1).astype(int)
        else:
            df["is_fallback"] = 1
        if "published_at" in df.columns:
            df["published_at_dt"] = normalize_published_at_series(df["published_at"].tolist())
        else:
            df["published_at_dt"] = pd.NaT
        df["normalized_title"] = df.get("title", pd.Series(index=df.index, dtype=str)).fillna("").astype(str).map(_normalize_news_text)
        df["normalized_summary"] = df.get("summary", pd.Series(index=df.index, dtype=str)).fillna("").astype(str).map(_normalize_news_text)
        df = df.sort_values(["ticker_norm", "relevance_score", "published_at_dt"], ascending=[True, False, False]).reset_index(drop=True)
        self.news_df = df
        if "ticker_norm" in df.columns:
            self._news_by_ticker = {
                str(ticker): group.reset_index(drop=True)
                for ticker, group in df.groupby("ticker_norm", sort=False)
            }

    async def get_stock_news(self, code: str, limit: int, name: str, target_date: date | None = None) -> List[NewsItem]:
        code = str(code).zfill(6)
        selected_date = target_date or date.today()
        normalized_name = _normalize_news_text(name)
        source_df = self._news_by_ticker.get(code)
        if source_df is not None and not source_df.empty:
            start, end = build_news_window(selected_date, **self._window_kwargs())
            s = source_df[(source_df["published_at_dt"] >= start) & (source_df["published_at_dt"] <= end)].copy()
            if not s.empty:
                if normalized_name:
                    direct_hits = s[
                        s["normalized_title"].astype(str).map(lambda value: normalized_name in value)
                        | s["normalized_summary"].astype(str).map(lambda value: normalized_name in value)
                    ]
                    if not direct_hits.empty:
                        s = direct_hits
                    else:
                        exact_title_hits = s[s["is_fallback"] == 0]
                        if not exact_title_hits.empty:
                            s = exact_title_hits
                        else:
                            return []

                s = s.head(max(1, limit))
                out: List[NewsItem] = []
                for _, r in s.iterrows():
                    url = str(r.get("url", "")).strip()
                    if not self._is_valid_news_url(url):
                        continue
                    p = None
                    if str(r.get("published_at", "")).strip():
                        try:
                            p = pd.to_datetime(r["published_at"]).to_pydatetime()
                        except Exception:
                            p = None
                    out.append(
                        NewsItem(
                            title=str(r.get("title", "")),
                            summary=str(r.get("summary", "")),
                            source=str(r.get("source", "Naver")),
                            published_at=p,
                            url=url,
                        )
                    )
                if out:
                    return out

        if self.allow_synthetic_fallback:
            return self._synthetic_news(code, limit, name)
        return []

    def _read_news_csv(self) -> Optional[pd.DataFrame]:
        if self.repo is None:
            return None
        try:
            df = self.repo.load_news_df()
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
            return None
        except Exception:
            return None

    @staticmethod
    def _is_valid_news_url(url: str) -> bool:
        return str(url).startswith("https://finance.naver.com/item/news_read.naver")

    def _synthetic_news(self, code: str, limit: int, name: str) -> List[NewsItem]:
        rng = random.Random(_stable_seed("news", code, date.today().isoformat()))
        pool = [
            ("수주 확대 기대", "신규 고객사 확대와 수주 증가 기대감이 반영되고 있습니다."),
            ("실적 개선 전망", "증권사 컨센서스 기준 다음 분기 이익 개선이 예상됩니다."),
            ("테마 모멘텀 부각", "관련 업종 강세에 따라 동반 상승 흐름이 관찰됩니다."),
            ("외국인 순매수 지속", "최근 5거래일 누적 외국인 순매수가 유입되고 있습니다."),
            ("기관 수급 개선", "기관 매수세가 강해지면서 변동성이 완화되는 모습입니다."),
        ]
        count = min(limit, max(0, rng.randint(1, limit)))
        selected = rng.sample(pool, count)
        now = datetime.now()
        items: List[NewsItem] = []
        for idx, (title, summary) in enumerate(selected, 1):
            items.append(
                NewsItem(
                    title=f"[{name}] {title}",
                    summary=f"{summary} ({describe_news_window(date.today(), **self._window_kwargs())} 기준 synthetic)",
                    source="SyntheticNews",
                    published_at=now - timedelta(hours=idx * 2),
                    url=f"https://example.com/news/{code}/{idx}",
                )
            )
        return items

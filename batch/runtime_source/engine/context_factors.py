from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable

import pandas as pd

from engine.models import IntradayFeatureData, IntradayPressureData, NewsAttentionData, SectorLeadershipData
from engine.news_window import build_news_window
from engine.theme_classifier import infer_theme


MAJOR_MEDIA_KEYWORDS = (
    "연합뉴스",
    "한국경제",
    "매일경제",
    "머니투데이",
    "서울경제",
    "조선비즈",
    "이데일리",
    "뉴스1",
    "SBS Biz",
    "MBC",
    "KBS",
    "YTN",
    "JTBC",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = " ".join(text.split())
    return "".join(ch for ch in text if ch.isalnum() or ("가" <= ch <= "힣"))


def _normalize_sector(sector: Any) -> str:
    text = str(sector or "").strip()
    return text if text else "General"


def _normalize_ticker(value: Any) -> str:
    return str(value or "").strip().zfill(6)


def _major_media_score(sources: Iterable[str]) -> bool:
    for source in sources:
        src = str(source or "").strip()
        if any(keyword in src for keyword in MAJOR_MEDIA_KEYWORDS):
            return True
    return False


def _parse_dt(value: Any) -> datetime | None:
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        if getattr(ts, "tzinfo", None) is not None:
            return ts.tz_convert(None).to_pydatetime() if hasattr(ts, "tz_convert") else ts.to_pydatetime().replace(tzinfo=None)
        return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else None
    except Exception:
        return None


class FactorContext:
    def __init__(
        self,
        *,
        snapshot_df: pd.DataFrame | None,
        news_df: pd.DataFrame | None,
        flows_df: pd.DataFrame | None,
        intraday_df: pd.DataFrame | None,
        intraday_snapshots_df: pd.DataFrame | None,
        condition_hits_df: pd.DataFrame | None,
        program_snapshots_df: pd.DataFrame | None,
        target_date: date,
    ) -> None:
        self.target_date = target_date
        self._sector_map: Dict[str, SectorLeadershipData] = {}
        self._ticker_sector_map: Dict[str, SectorLeadershipData] = {}
        self._intraday_history_map: Dict[str, pd.DataFrame] = {}
        self._condition_hits_map: Dict[str, Dict[str, Any]] = {}
        self._program_delta_map: Dict[str, int] = {}
        self._news_rows_map: Dict[str, pd.DataFrame] = {}

        self.snapshot_df = self._prepare_snapshot(snapshot_df)
        self.all_news_df = self._prepare_news(news_df, filter_window=False)
        self.news_df = self._prepare_news(news_df, filter_window=True)
        self.flows_df = self._prepare_flows(flows_df)
        self.intraday_df = self._prepare_intraday(intraday_df)
        self.intraday_snapshots_df = self._prepare_intraday_snapshots(intraday_snapshots_df)
        self.condition_hits_df = self._prepare_condition_hits(condition_hits_df)
        self.program_snapshots_df = self._prepare_program_snapshots(program_snapshots_df)

        self._build_sector_maps()
        self._build_intraday_history_map()
        self._build_condition_hits_map()
        self._build_program_delta_map()
        self._build_news_rows_map()

    def _prepare_snapshot(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["ticker_norm"] = out["ticker"].map(_normalize_ticker) if "ticker" in out.columns else ""
        if "sector" in out.columns:
            out["sector_key"] = out["sector"].map(_normalize_sector)
        else:
            out["sector_key"] = ""
        if "name" in out.columns:
            out["sector_key"] = [
                _normalize_sector(sector) if str(sector or "").strip() and str(sector or "").strip() != "General" else infer_theme(str(name or ""))
                for sector, name in zip(out["sector_key"].tolist(), out["name"].tolist())
            ]
        out["sector_key"] = out["sector_key"].map(_normalize_sector)
        if "change_pct" in out.columns:
            out["change_pct"] = pd.to_numeric(out["change_pct"], errors="coerce").fillna(0.0)
        else:
            out["change_pct"] = 0.0
        if "trading_value" in out.columns:
            out["trading_value"] = pd.to_numeric(out["trading_value"], errors="coerce").fillna(0.0)
        else:
            out["trading_value"] = 0.0
        return out

    def _prepare_news(self, df: pd.DataFrame | None, *, filter_window: bool) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["ticker_norm"] = out["ticker"].map(_normalize_ticker) if "ticker" in out.columns else ""
        out["published_at_dt"] = pd.to_datetime(out["published_at"], errors="coerce") if "published_at" in out.columns else pd.NaT
        try:
            out["published_at_dt"] = out["published_at_dt"].dt.tz_localize(None)
        except Exception:
            pass
        out["normalized_title"] = out["title"].fillna("").astype(str).map(_normalize_text) if "title" in out.columns else ""
        if filter_window:
            start, end = build_news_window(self.target_date)
            out = out[(out["published_at_dt"] >= start) & (out["published_at_dt"] <= end)]
        return out

    def _prepare_flows(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["ticker_norm"] = out["ticker"].map(_normalize_ticker) if "ticker" in out.columns else ""
        for column in ["foreign_net_buy", "inst_net_buy", "retail_net_buy"]:
            if column in out.columns:
                out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
            else:
                out[column] = 0.0
        return out

    def _prepare_intraday(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["ticker_norm"] = out["ticker"].map(_normalize_ticker) if "ticker" in out.columns else ""
        return out

    def _prepare_intraday_snapshots(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["ticker_norm"] = out["ticker"].map(_normalize_ticker) if "ticker" in out.columns else ""
        out["snapshot_time_dt"] = pd.to_datetime(out["snapshot_time"], errors="coerce") if "snapshot_time" in out.columns else pd.NaT
        try:
            out["snapshot_time_dt"] = out["snapshot_time_dt"].dt.tz_localize(None)
        except Exception:
            pass
        for column in [
            "execution_strength",
            "orderbook_imbalance",
            "minute_breakout_score",
            "volume_surge_ratio",
            "orderbook_surge_ratio",
            "acc_trade_value",
            "acc_trade_volume",
        ]:
            if column in out.columns:
                out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)
        return out.sort_values(["ticker_norm", "snapshot_time_dt"])

    def _prepare_condition_hits(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["ticker_norm"] = out["ticker"].map(_normalize_ticker) if "ticker" in out.columns else ""
        if "hit_count" in out.columns:
            out["hit_count"] = pd.to_numeric(out["hit_count"], errors="coerce").fillna(0).astype(int)
        else:
            out["hit_count"] = 0
        return out

    def _prepare_program_snapshots(self, df: pd.DataFrame | None) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        out = df.copy()
        out["market_norm"] = out["market"].astype(str).str.upper() if "market" in out.columns else ""
        out["snapshot_time_dt"] = pd.to_datetime(out["snapshot_time"], errors="coerce") if "snapshot_time" in out.columns else pd.NaT
        try:
            out["snapshot_time_dt"] = out["snapshot_time_dt"].dt.tz_localize(None)
        except Exception:
            pass
        if "total_net" in out.columns:
            out["total_net"] = pd.to_numeric(out["total_net"], errors="coerce").fillna(0.0)
        else:
            out["total_net"] = 0.0
        return out.sort_values(["market_norm", "snapshot_time_dt"])

    def _build_sector_maps(self) -> None:
        if self.snapshot_df.empty:
            return

        rows = self.snapshot_df.copy()
        if not self.flows_df.empty:
            latest_flow = self.flows_df.sort_values("date").groupby("ticker_norm", as_index=False).tail(1)
            latest_flow = latest_flow[["ticker_norm", "foreign_net_buy", "inst_net_buy"]]
            rows = rows.merge(latest_flow, on="ticker_norm", how="left")
        else:
            rows["foreign_net_buy"] = 0.0
            rows["inst_net_buy"] = 0.0

        sector_news_counts = defaultdict(int)
        if not self.all_news_df.empty:
            news_title_map = {
                str(ticker): [str(value) for value in group.get("title", pd.Series(dtype=str)).fillna("").tolist() if str(value).strip()]
                for ticker, group in self.all_news_df.groupby("ticker_norm", sort=False)
            }
            rows["sector_key"] = [
                infer_theme(str(name or ""), texts=news_title_map.get(str(ticker), []), fallback=str(sector or "General"))
                for ticker, name, sector in zip(rows["ticker_norm"].tolist(), rows.get("name", pd.Series(dtype=str)).tolist(), rows["sector_key"].tolist())
            ]
        if not self.news_df.empty:
            recent_news = self.news_df[self.news_df["ticker_norm"].isin(rows["ticker_norm"].tolist())].copy()
            recent_news = recent_news[recent_news["published_at_dt"].notna()]
            if not recent_news.empty:
                tickers_to_sector = {
                    str(row["ticker_norm"]): str(row["sector_key"])
                    for _, row in rows[["ticker_norm", "sector_key"]].drop_duplicates().iterrows()
                }
                for _, news_row in recent_news.iterrows():
                    sector_key = tickers_to_sector.get(str(news_row.get("ticker_norm", "")), "General")
                    sector_news_counts[sector_key] += 1

        sector_stats: list[dict[str, Any]] = []
        for sector_key, group in rows.groupby("sector_key", sort=False):
            advancers = int((group["change_pct"] > 0).sum())
            decliners = int((group["change_pct"] < 0).sum())
            total_tv = float(group["trading_value"].sum())
            avg_change = float(group["change_pct"].mean())
            breadth_ratio = advancers / max(len(group), 1)
            raw_score = (avg_change * 0.45) + (breadth_ratio * 5.0) + (total_tv / 100_000_000_000 * 0.18) + (sector_news_counts[sector_key] * 0.12)
            ordered = group.assign(
                leader_raw=(group["change_pct"] * 0.55) + ((group["trading_value"] / 100_000_000_000) * 0.25) + ((group["foreign_net_buy"] + group["inst_net_buy"]) / 10_000_000_000 * 0.20)
            ).sort_values(["leader_raw", "change_pct", "trading_value"], ascending=[False, False, False])
            top_row = ordered.iloc[0]
            sector_stats.append(
                {
                    "sector_key": str(sector_key),
                    "sector_count": int(len(group)),
                    "sector_avg_change_pct": round(avg_change, 4),
                    "sector_total_trading_value": int(total_tv),
                    "raw_score": raw_score,
                    "top_ticker": str(top_row.get("ticker_norm", "")),
                    "top_stock_name": str(top_row.get("name", "")),
                    "sector_news_count": int(sector_news_counts[sector_key]),
                    "ordered": ordered,
                }
            )

        sector_stats.sort(key=lambda item: item["raw_score"], reverse=True)
        for idx, item in enumerate(sector_stats, start=1):
            sector_score = 2.0 if idx <= 2 else 1.0 if idx <= 4 else 0.0
            item_data = SectorLeadershipData(
                sector_key=item["sector_key"],
                sector_score=sector_score,
                sector_rank=idx,
                sector_count=item["sector_count"],
                sector_avg_change_pct=item["sector_avg_change_pct"],
                sector_total_trading_value=item["sector_total_trading_value"],
                top_ticker=item["top_ticker"],
                top_stock_name=item["top_stock_name"],
                sector_news_count=item["sector_news_count"],
            )
            self._sector_map[item["sector_key"]] = item_data
            ordered = item["ordered"]
            for leader_rank, (_, row) in enumerate(ordered.iterrows(), start=1):
                leader_score = 2.0 if leader_rank == 1 else 1.0 if leader_rank == 2 else 0.0
                self._ticker_sector_map[str(row.get("ticker_norm", ""))] = SectorLeadershipData(
                    sector_key=item_data.sector_key,
                    sector_score=item_data.sector_score,
                    sector_rank=item_data.sector_rank,
                    sector_count=item_data.sector_count,
                    sector_avg_change_pct=item_data.sector_avg_change_pct,
                    sector_total_trading_value=item_data.sector_total_trading_value,
                    leader_rank=leader_rank,
                    leader_score=leader_score,
                    is_leader=leader_rank == 1,
                    top_ticker=item_data.top_ticker,
                    top_stock_name=item_data.top_stock_name,
                    sector_news_count=item_data.sector_news_count,
                )

    def _build_intraday_history_map(self) -> None:
        if self.intraday_snapshots_df.empty:
            return
        self._intraday_history_map = {
            str(ticker): group.reset_index(drop=True)
            for ticker, group in self.intraday_snapshots_df.groupby("ticker_norm", sort=False)
        }

    def _build_condition_hits_map(self) -> None:
        if self.condition_hits_df.empty:
            return
        for ticker, group in self.condition_hits_df.groupby("ticker_norm", sort=False):
            self._condition_hits_map[str(ticker)] = {
                "total_hits": int(group["hit_count"].sum()) if "hit_count" in group.columns else int(len(group)),
                "condition_names": [str(v).strip() for v in group.get("condition_name", pd.Series(dtype=str)).fillna("").tolist() if str(v).strip()],
            }

    def _build_program_delta_map(self) -> None:
        if self.program_snapshots_df.empty:
            return
        for market, group in self.program_snapshots_df.groupby("market_norm", sort=False):
            if len(group) < 2:
                self._program_delta_map[str(market)] = 0
                continue
            last = group.iloc[-1]
            prev = group.iloc[-2]
            self._program_delta_map[str(market)] = _safe_int(last.get("total_net"), 0) - _safe_int(prev.get("total_net"), 0)

    def _build_news_rows_map(self) -> None:
        if self.news_df.empty:
            return
        self._news_rows_map = {
            str(ticker): group.reset_index(drop=True)
            for ticker, group in self.news_df.groupby("ticker_norm", sort=False)
        }

    def sector_for_stock(self, ticker: str, sector: str) -> SectorLeadershipData:
        normalized_ticker = _normalize_ticker(ticker)
        factor = self._ticker_sector_map.get(normalized_ticker)
        if factor is not None:
            return factor
        sector_key = _normalize_sector(sector)
        return self._sector_map.get(sector_key, SectorLeadershipData(sector_key=sector_key))

    def intraday_for_stock(self, ticker: str, market: str, intraday_feature: IntradayFeatureData) -> IntradayPressureData:
        normalized_ticker = _normalize_ticker(ticker)
        history = self._intraday_history_map.get(normalized_ticker)
        condition_meta = self._condition_hits_map.get(normalized_ticker, {})
        program_delta = self._program_delta_map.get(str(market or "").upper(), 0)

        execution_delta = 0.0
        orderbook_delta = 0.0
        snapshot_count = 0
        if history is not None and not history.empty:
            snapshot_count = int(len(history))
            baseline = history.iloc[:-1] if len(history) > 1 else history.iloc[:0]
            if not baseline.empty:
                execution_delta = intraday_feature.execution_strength - _safe_float(baseline["execution_strength"].median(), 0.0)
                orderbook_delta = intraday_feature.orderbook_imbalance - _safe_float(baseline["orderbook_imbalance"].median(), 0.0)

        score = 0.0
        if intraday_feature.execution_strength >= 110:
            score += 0.6
        elif intraday_feature.execution_strength >= 100:
            score += 0.3
        if intraday_feature.orderbook_imbalance >= 0.10:
            score += 0.5
        elif intraday_feature.orderbook_imbalance >= 0.03:
            score += 0.25
        if intraday_feature.minute_pattern == "rebreakout":
            score += 0.4
        elif intraday_feature.minute_pattern == "range" and intraday_feature.minute_breakout_score > 0:
            score += 0.2
        if intraday_feature.volume_surge_ratio >= 1.4:
            score += 0.3
        if intraday_feature.orderbook_surge_ratio >= 1.2:
            score += 0.2
        if execution_delta >= 8:
            score += 0.3
        if orderbook_delta >= 0.08:
            score += 0.3
        if _safe_int(condition_meta.get("total_hits"), 0) > 0:
            score += 0.2
        if program_delta >= 100_000_000_000:
            score += 0.3
        elif program_delta <= -100_000_000_000:
            score -= 0.4

        score = max(0.0, min(2.0, score))
        if score >= 1.4:
            status = "STRONG"
        elif score >= 0.7:
            status = "SUPPORTIVE"
        elif score > 0:
            status = "MIXED"
        else:
            status = "WEAK"

        return IntradayPressureData(
            score=round(score, 2),
            pressure_status=status,
            execution_strength=intraday_feature.execution_strength,
            execution_delta=round(execution_delta, 2),
            orderbook_imbalance=intraday_feature.orderbook_imbalance,
            orderbook_delta=round(orderbook_delta, 4),
            minute_pattern=intraday_feature.minute_pattern,
            minute_breakout_score=intraday_feature.minute_breakout_score,
            volume_surge_ratio=intraday_feature.volume_surge_ratio,
            orderbook_surge_ratio=intraday_feature.orderbook_surge_ratio,
            condition_hit_count=_safe_int(condition_meta.get("total_hits"), intraday_feature.condition_hit_count),
            program_delta=program_delta,
            snapshot_count=snapshot_count,
        )

    def news_attention_for_stock(
        self,
        ticker: str,
        *,
        news_items: list[dict[str, Any]],
        llm_meta: Dict[str, Any] | None,
    ) -> NewsAttentionData:
        normalized_ticker = _normalize_ticker(ticker)
        frame = self._news_rows_map.get(normalized_ticker, pd.DataFrame())
        article_count = int(len(news_items))
        sources = [str(item.get("source", "") or "").strip() for item in news_items]
        media_count = len({src for src in sources if src})
        strong_broadcast = _major_media_score(sources)
        now = datetime.now(timezone.utc).astimezone().replace(tzinfo=None)
        freshness_minutes = 0
        published_times = [_parse_dt(item.get("published_at")) for item in news_items]
        published_times = [value for value in published_times if value is not None]
        if published_times:
            freshest = max(published_times)
            freshness_minutes = max(0, int((now - freshest).total_seconds() // 60))

        material_strength = _safe_float((llm_meta or {}).get("material_strength"), 0.0)
        attention_score = _safe_float((llm_meta or {}).get("attention_score"), 0.0)
        novelty_score = _safe_float((llm_meta or {}).get("novelty_score"), 0.0)
        entity_confidence = _safe_float((llm_meta or {}).get("entity_confidence"), 0.0)
        if material_strength <= 0:
            material_strength = min(3.0, article_count * 0.7 + (1.0 if strong_broadcast else 0.0))
        if attention_score <= 0:
            attention_score = min(2.0, article_count * 0.4 + media_count * 0.25 + (0.4 if strong_broadcast else 0.0))
        if novelty_score <= 0:
            novelty_score = 1.4 if freshness_minutes <= 120 and article_count > 0 else 0.8 if article_count > 0 else 0.0
        if entity_confidence <= 0:
            entity_confidence = 1.0 if article_count > 0 else 0.0

        category = str((llm_meta or {}).get("category", "") or "")
        tone = str((llm_meta or {}).get("tone", "") or "")
        if frame is not None and not frame.empty and article_count <= 0:
            media_count = max(media_count, int(frame.get("source", pd.Series(dtype=str)).astype(str).nunique()))

        return NewsAttentionData(
            material_strength=round(material_strength, 2),
            attention_score=round(attention_score, 2),
            novelty_score=round(novelty_score, 2),
            entity_confidence=round(entity_confidence, 2),
            media_count=media_count,
            article_count=article_count,
            strong_broadcast=strong_broadcast,
            category=category,
            tone=tone,
            freshness_minutes=freshness_minutes,
        )

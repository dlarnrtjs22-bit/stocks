from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine.config import Grade, SignalConfig
from engine.models import (
    ChartData,
    ChecklistDetail,
    IntradayPressureData,
    MarketContextData,
    NewsItem,
    NewsAttentionData,
    ProgramTradeData,
    ScoreDetail,
    SectorLeadershipData,
    StockData,
    SupplyData,
)


class Scorer:
    def __init__(self, config: SignalConfig):
        self.config = config

    def calculate(
        self,
        stock: StockData,
        charts: List[ChartData],
        news_list: List[NewsItem],
        supply: Optional[SupplyData],
        market_context: Optional[MarketContextData],
        program_trade: Optional[ProgramTradeData],
        sector_leadership: Optional[SectorLeadershipData],
        intraday_pressure: Optional[IntradayPressureData],
        news_attention: Optional[NewsAttentionData],
        llm_result: Optional[Dict],
    ) -> Tuple[ScoreDetail, ChecklistDetail]:
        checklist = ChecklistDetail()
        score = ScoreDetail()

        checklist.has_news = len(news_list) > 0
        checklist.news_sources = sorted(
            {n.source for n in news_list if n.source and n.source != "SyntheticNews"}
        )

        llm_score = int(getattr(self.config, "default_news_score", 1) or 1)
        llm_reason = "AI 분석 결과가 없어 기본 뉴스 점수 1점을 적용했습니다."
        llm_meta: Dict = {"status": "NO_RESULT"}
        if llm_result:
            llm_score = int(llm_result.get("score", llm_score) or llm_score)
            llm_reason = str(llm_result.get("reason", "") or "").strip() or llm_reason
            if isinstance(llm_result.get("meta"), dict):
                llm_meta = dict(llm_result.get("meta") or {})
            else:
                llm_meta = {
                    "status": str(llm_result.get("status", "NO_RESULT") or "NO_RESULT"),
                    "provider": str(llm_result.get("provider", "") or ""),
                    "model": str(llm_result.get("model", "") or ""),
                    "reasoning_effort": str(llm_result.get("reasoning_effort", "") or ""),
                }

        default_news_score = int(getattr(self.config, "default_news_score", 1) or 1)
        default_news_score = max(0, min(3, default_news_score))
        no_news_score = int(getattr(self.config, "no_news_score", 0) or 0)
        no_news_score = max(0, min(3, no_news_score))

        if not news_list:
            score.news = no_news_score
            llm_reason = "당일 및 전일 장마감 이후 종목 직접 관련 뉴스가 없어 뉴스 점수 0점을 적용했습니다."
            llm_meta = {**llm_meta, "status": "NO_NEWS"}
        elif llm_result and str(llm_meta.get("status", "")).upper() == "OK":
            score.news = max(0, min(3, llm_score))
        else:
            score.news = default_news_score

        score.llm_reason = llm_reason
        score.llm_meta = llm_meta

        tv = stock.trading_value
        if tv >= 1_000_000_000_000:
            score.volume = 3
        elif tv >= 500_000_000_000:
            score.volume = 2
        elif tv >= 100_000_000_000:
            score.volume = 1
        else:
            score.volume = 0
        checklist.volume_surge = score.volume >= 2

        recent_high = max((c.high for c in charts[-20:]), default=stock.close)
        checklist.is_breakout = stock.close >= recent_high * 0.995
        checklist.is_new_high = bool(stock.high_52w and stock.close >= stock.high_52w * 0.98)
        if checklist.is_new_high or checklist.is_breakout:
            score.chart = 2
        elif stock.change_pct >= 5:
            score.chart = 1

        if charts:
            last = charts[-1]
            bullish = last.close > last.open
            if bullish and stock.change_pct >= 4:
                score.candle = 1

        if len(charts) >= 25:
            recent = charts[-5:]
            prev = charts[-25:-5]
            recent_range = sum((c.high - c.low) / max(c.close, 1e-6) for c in recent) / len(recent)
            prev_range = sum((c.high - c.low) / max(c.close, 1e-6) for c in prev) / len(prev)
            if recent_range < prev_range * 0.8:
                score.consolidation = 1

        if supply:
            checklist.supply_positive = supply.foreign_buy_5d > 0 and supply.inst_buy_5d > 0
            if checklist.supply_positive:
                score.supply = 2
            elif supply.foreign_buy_5d > 0 or supply.inst_buy_5d > 0:
                score.supply = 1

        if market_context:
            breadth_delta = int(market_context.rise_count) - int(market_context.fall_count)
            checklist.market_supportive = bool(
                market_context.change_pct > 0
                or (market_context.change_pct >= -0.3 and breadth_delta > 0)
            )
            if checklist.market_supportive:
                score.market = 1

        if program_trade:
            supply_positive = bool(supply and (supply.foreign_buy_5d > 0 or supply.inst_buy_5d > 0))
            checklist.program_supportive = bool(
                int(program_trade.total_net) > 0
                and (int(program_trade.non_arbitrage_net) >= 0 or supply_positive or stock.change_pct > 0)
            )
            if checklist.program_supportive:
                score.program = 1

        if sector_leadership:
            checklist.sector_supportive = bool(
                sector_leadership.sector_rank <= 4 and sector_leadership.sector_score >= 1
            )
            checklist.leader_confirmed = bool(
                sector_leadership.leader_rank <= 2 and sector_leadership.leader_score >= 1
            )
            if sector_leadership.sector_rank <= 2 and sector_leadership.sector_score >= 2:
                score.sector = 2
            elif sector_leadership.sector_rank <= 4:
                score.sector = 1

            if sector_leadership.is_leader and sector_leadership.leader_score >= 2:
                score.leader = 2
            elif sector_leadership.leader_rank <= 2:
                score.leader = 1

        if intraday_pressure:
            checklist.intraday_supportive = bool(intraday_pressure.score >= 0.7)
            if intraday_pressure.score >= 1.4:
                score.intraday = 2
            elif intraday_pressure.score >= 0.7:
                score.intraday = 1

        if news_attention:
            checklist.news_attention_high = bool(
                news_attention.attention_score >= 1.0
                or news_attention.strong_broadcast
                or news_attention.media_count >= 3
            )
            if news_attention.article_count <= 0:
                score.news_attention = 0
            elif news_attention.attention_score >= 1.5 and news_attention.entity_confidence >= 0.8:
                score.news_attention = 2
            elif news_attention.attention_score >= 0.7 and news_attention.entity_confidence >= 0.5:
                score.news_attention = 1

        score.finalize()
        return score, checklist

    def determine_grade(self, stock: StockData, score: ScoreDetail) -> Grade:
        for grade in (Grade.S, Grade.A, Grade.B):
            cfg = self.config.grade_configs[grade]
            if (
                stock.trading_value >= cfg.min_trading_value
                and cfg.min_change_pct <= stock.change_pct <= cfg.max_change_pct
                and score.total >= cfg.min_score
            ):
                return grade
        return Grade.C

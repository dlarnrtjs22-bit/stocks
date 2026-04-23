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
    StockProgramData,
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
        stock_program: Optional[StockProgramData],
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

        # Design Ref: Design §5 Module B — 실체성 있는 뉴스 카운트 (수급단타왕 "실체없는 테마 경계")
        # LLM 분석 OK + material_strength >= 0.3 만 실체 있는 재료로 인정
        # decision_policy의 NEWS_BLOCKED 판단에 이 값을 쓰면 fallback 1점 뉴스가 매수 허용을 우회하는 허점 제거
        material_threshold = 0.3
        material_strength = 0.0
        if isinstance(llm_meta, dict):
            try:
                material_strength = float(llm_meta.get("material_strength", 0) or 0)
            except (TypeError, ValueError):
                material_strength = 0.0
        is_material = (
            len(news_list) > 0
            and str(llm_meta.get("status", "")).upper() == "OK"
            and material_strength >= material_threshold
        )
        score.material_news_count = int(is_material)

        # 실체없는 테마 감점: attention만 높고 material 낮으면 -1 (news_attention에서 차감)
        try:
            attention_score = float(llm_meta.get("attention_score", 0) or 0) if isinstance(llm_meta, dict) else 0.0
        except (TypeError, ValueError):
            attention_score = 0.0
        # attention 높은데 material 낮음 = 실체없는 테마 → score.news가 2점 이상이면 1점으로 감점
        if attention_score >= 1.5 and material_strength < material_threshold and score.news >= 2:
            score.news = max(0, score.news - 1)
            llm_reason = (llm_reason + " [실체없는 테마 감점 -1]").strip()

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
            # Design Ref: Design §5 Module B — 수급단타왕 "매일매일 매집" 연속성 보너스
            # 외인 + 기관 모두 N일 이상 연속 순매수면 +1점 (pipeline에서 필드 채워야 작동)
            from engine.scoring_constants import SUPPLY_CONTINUITY_MIN_DAYS
            fgn_days = int(getattr(supply, "continuity_days_foreign", 0) or 0)
            inst_days = int(getattr(supply, "continuity_days_institution", 0) or 0)
            if fgn_days >= SUPPLY_CONTINUITY_MIN_DAYS and inst_days >= SUPPLY_CONTINUITY_MIN_DAYS:
                score.supply_continuity = 1

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

        if stock_program:
            latest_ratio = stock_program.latest_net_buy_amt / max(float(stock.trading_value or 0), 1.0)
            late_ratio_10 = stock_program.delta_10m_amt / max(float(stock.trading_value or 0), 1.0)
            late_ratio_30 = stock_program.delta_30m_amt / max(float(stock.trading_value or 0), 1.0)
            checklist.stock_program_supportive = bool(
                stock_program.latest_net_buy_amt > 0
                and (stock_program.delta_10m_amt > 0 or stock_program.delta_30m_amt > 0)
            )
            if (
                stock_program.delta_10m_amt >= 8_000_000_000
                or stock_program.delta_30m_amt >= 15_000_000_000
                or late_ratio_10 >= 0.008
                or late_ratio_30 >= 0.015
                or latest_ratio >= 0.02
            ):
                score.stock_program = 2
            elif (
                stock_program.latest_net_buy_amt > 0
                or stock_program.daily_net_buy_amt_5d > 0
                or late_ratio_10 >= 0.003
                or late_ratio_30 >= 0.006
            ):
                score.stock_program = 1

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

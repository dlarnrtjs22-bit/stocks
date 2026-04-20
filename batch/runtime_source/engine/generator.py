"""
시그널 생성기 (Main Engine)
- Collector로부터 데이터 수집
- Scorer로 점수 계산
- PositionSizer로 자금 관리
- 최종 Signal 생성
"""

import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
import time
import sys
import os
import traceback

# 모듈 경로 추가 (상위 디렉토리를 경로에 추가)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.config import SignalConfig, Grade
from engine.context_factors import FactorContext
from engine.decision_policy import apply_market_grade_policy
from engine.models import (
    StockData, Signal, SignalStatus, 
    ScoreDetail, ChecklistDetail, ScreenerResult, ChartData
)
from engine.collectors import KRXCollector, EnhancedNewsCollector
from engine.external_market_context import get_external_market_context
from engine.freshness import assert_data_ready_for_run


SEOUL_TZ = ZoneInfo("Asia/Seoul")
from engine.news_window import describe_news_window
from engine.scorer import Scorer
from engine.scoring_constants import TOTAL_RULE_SCORE_MAX
from engine.position_sizer import PositionSizer
from engine.llm_analyzer import LLMAnalyzer
from supabase_py.db import is_supabase_backend
from supabase_py.repository import SupabaseRepository


def _grade_value(value: Grade | str) -> str:
    return value.value if isinstance(value, Grade) else str(value)


def _reference_trade_date(freshness_report: Dict[str, Any]) -> date:
    reference = str(freshness_report.get("reference_data_time", "") or "").strip()
    if len(reference) >= 10:
        try:
            return date.fromisoformat(reference[:10])
        except ValueError:
            pass
    return date.today()


class SignalGenerator:
    """종가베팅 시그널 생성기 (v2)"""
    
    def __init__(
        self,
        config: SignalConfig = None,
        capital: float = 10_000_000,
    ):
        """
        Args:
            capital: 총 자본금 (기본 5천만원)
            config: 설정 (기본 설정 사용)
        """
        self.config = config or SignalConfig()
        self.capital = capital
        
        self.scorer = Scorer(self.config)
        self.position_sizer = PositionSizer(capital, self.config)
        self.llm_analyzer = LLMAnalyzer() # API Key from env
        self.max_llm_calls = max(0, int(os.getenv("LLM_MAX_CALLS_PER_RUN", "10") or 10))
        self.max_overall_ai_calls = max(0, int(os.getenv("LLM_MAX_OVERALL_ANALYSIS", "5") or 5))
        self._llm_calls = 0
        self.external_market_context: Dict[str, Any] = {}
        self._factor_context: Optional[FactorContext] = None
        
        self._collector: Optional[KRXCollector] = None
        self._news: Optional[EnhancedNewsCollector] = None
    
    async def __aenter__(self):
        self._collector = KRXCollector(self.config)
        await self._collector.__aenter__()
        
        self._news = EnhancedNewsCollector(self.config)
        await self._news.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._collector:
            await self._collector.__aexit__(exc_type, exc_val, exc_tb)
        if self._news:
            await self._news.__aexit__(exc_type, exc_val, exc_tb)
    
    async def generate(
        self,
        target_date: date = None,
        markets: List[str] = None,
        top_n: int = 30,
    ) -> List[Signal]:
        """
        시그널 생성
        
        Args:
            target_date: 대상 날짜 (기본: 오늘)
            markets: 대상 시장 (기본: KOSPI, KOSDAQ)
            top_n: 상승률 상위 N개 종목
        
        Returns:
            Signal 리스트 (등급순 정렬)
        """
        target_date = target_date or date.today()
        # markets = markets or ["KOSPI", "KOSDAQ"]
        markets = markets or ["KOSPI", "KOSDAQ"] 
        self._llm_calls = 0
        self.external_market_context = get_external_market_context()
        self._factor_context = FactorContext(
            snapshot_df=self._collector.snapshot_df if self._collector else None,
            news_df=self._news.news_df if self._news else None,
            flows_df=self._collector.flows_df if self._collector else None,
            intraday_df=self._collector.intraday_df if self._collector else None,
            intraday_snapshots_df=self._collector.intraday_snapshots_df if self._collector else None,
            condition_hits_df=self._collector.condition_hits_df if self._collector else None,
            program_snapshots_df=self._collector.program_snapshots_df if self._collector else None,
            target_date=target_date,
        )
        
        all_signals = []
        
        for market in markets:
            print(f"\n[{market}] 상승률 상위 종목 스크리닝...")
            
            # 1. 상승률 상위 종목 조회
            candidates = await self._collector.get_top_gainers(market, top_n)
            print(f"  - 1차 필터 통과: {len(candidates)}개")
            
            # 2. 각 종목 분석
            for i, stock in enumerate(candidates):
                print(f"  [{i+1}/{len(candidates)}] {stock.name}({stock.code}) 분석 중...", end='\r')
                
                signal = await self._analyze_stock(stock, target_date)
                
                if signal:
                    all_signals.append(signal)
                    base_grade = str(signal.ai_overall.get("base_grade", signal.grade.value) or signal.grade.value)
                    market_policy = signal.ai_overall.get("market_policy", {}) if isinstance(signal.ai_overall, dict) else {}
                    grade_note = ""
                    if base_grade != signal.grade.value:
                        grade_note = f" [{base_grade}->{signal.grade.value} {market_policy.get('market_status', '')}]"
                    if signal.grade != Grade.C:
                        print(f"\n    [OK] {stock.name}: {signal.grade.value}급 시그널 생성! (점수: {signal.score.total}){grade_note}")
                    else:
                        print(f"\n    - {stock.name}: C등급 보관 (점수: {signal.score.total}){grade_note}")
                
                # Rate limiting
                # await asyncio.sleep(0.1) # 너무 느려지면 제거
        
        # 3. 등급순 정렬 (S > A > B)
        grade_order = {Grade.S: 0, Grade.A: 1, Grade.B: 2, Grade.C: 3}
        all_signals.sort(key=lambda s: (grade_order[s.grade], -s.score.total))

        # 4. 상위 N개에 대해 규칙점수 기반 종합 AI 의견 생성
        await self._apply_overall_ai_topk(all_signals)
        
        print(f"\n총 {len(all_signals)}개 시그널 생성 완료")
        return all_signals

    async def _apply_overall_ai_topk(self, signals: List[Signal]) -> None:
        if not signals:
            return
        top_k = min(len(signals), self.max_overall_ai_calls)
        # Align overall AI targets with the same score-driven shortlist the UI highlights.
        initial_order = {id(sig): idx for idx, sig in enumerate(signals)}
        ai_candidates = [
            sig for sig in signals
            if str(sig.ai_overall.get("base_grade", _grade_value(sig.grade)) or _grade_value(sig.grade)).upper() in {"S", "A", "B"}
        ]
        ai_target_ids = {
            id(sig)
            for sig in sorted(
                ai_candidates,
                key=lambda sig: (
                    -int(sig.score.total or 0),
                    initial_order[id(sig)],
                    -int(sig.trading_value or 0),
                ),
            )[:top_k]
        }
        if top_k <= 0:
            for sig in signals:
                metrics = {
                    "grade": _grade_value(sig.grade),
                    "base_grade": str(sig.ai_overall.get("base_grade", _grade_value(sig.grade)) or _grade_value(sig.grade)),
                    "market_policy": dict(sig.ai_overall.get("market_policy", {})) if isinstance(sig.ai_overall.get("market_policy"), dict) else {},
                    "market": sig.market,
                    "change_pct": sig.change_pct,
                    "trading_value": sig.trading_value,
                    "entry_price": sig.entry_price,
                    "current_price": sig.current_price,
                    "target_price": sig.target_price,
                    "stop_price": sig.stop_price,
                    "foreign_5d": sig.foreign_5d,
                    "inst_5d": sig.inst_5d,
                    "market_context": dict(sig.ai_overall.get("market_context", {})) if isinstance(sig.ai_overall.get("market_context"), dict) else {},
                    "program_context": dict(sig.ai_overall.get("program_context", {})) if isinstance(sig.ai_overall.get("program_context"), dict) else {},
                    "external_market_context": dict(sig.ai_overall.get("external_market_context", {})) if isinstance(sig.ai_overall.get("external_market_context"), dict) else dict(self.external_market_context),
                    "intraday_context": dict(sig.ai_overall.get("intraday_context", {})) if isinstance(sig.ai_overall.get("intraday_context"), dict) else {},
                    "fresh_news_count": len(sig.news_items[:3] if isinstance(sig.news_items, list) else []),
                    "news_window_label": str(sig.ai_overall.get("news_window_label", "") or "") if isinstance(sig.ai_overall, dict) else "",
                }
                fallback = self.llm_analyzer.build_rule_based_overall(
                    stock_name=sig.stock_name,
                    rule_scores={
                        "news": sig.score.news,
                        "supply": sig.score.supply,
                        "chart": sig.score.chart,
                        "volume": sig.score.volume,
                        "candle": sig.score.candle,
                        "consolidation": sig.score.consolidation,
                        "market": sig.score.market,
                        "program": sig.score.program,
                        "sector": sig.score.sector,
                        "leader": sig.score.leader,
                        "intraday": sig.score.intraday,
                        "news_attention": sig.score.news_attention,
                        "total": sig.score.total,
                    },
                    metrics=metrics,
                    news_items=sig.news_items[:3] if isinstance(sig.news_items, list) else [],
                    status="DISABLED",
                    reason="AI 종합평가 비활성화 상태입니다.",
                )
                fallback.setdefault("market_context", metrics["market_context"])
                fallback.setdefault("program_context", metrics["program_context"])
                fallback.setdefault("intraday_context", metrics["intraday_context"])
                fallback.setdefault("external_market_context", metrics["external_market_context"])
                fallback.setdefault("market_policy", metrics["market_policy"])
                fallback.setdefault("base_grade", metrics["base_grade"])
                sig.ai_overall = fallback
            return

        for idx, sig in enumerate(signals):
            rule_scores = {
                "news": sig.score.news,
                "supply": sig.score.supply,
                "chart": sig.score.chart,
                "volume": sig.score.volume,
                "candle": sig.score.candle,
                "consolidation": sig.score.consolidation,
                "market": sig.score.market,
                "program": sig.score.program,
                "stock_program": sig.score.stock_program,
                "sector": sig.score.sector,
                "leader": sig.score.leader,
                "intraday": sig.score.intraday,
                "news_attention": sig.score.news_attention,
                "total": sig.score.total,
            }
            metrics = {
                "grade": _grade_value(sig.grade),
                "base_grade": str(sig.ai_overall.get("base_grade", _grade_value(sig.grade)) or _grade_value(sig.grade)),
                "market_policy": dict(sig.ai_overall.get("market_policy", {})) if isinstance(sig.ai_overall.get("market_policy"), dict) else {},
                "market": sig.market,
                "change_pct": sig.change_pct,
                "trading_value": sig.trading_value,
                "entry_price": sig.entry_price,
                "current_price": sig.current_price,
                "target_price": sig.target_price,
                "stop_price": sig.stop_price,
                "foreign_5d": sig.foreign_5d,
                "inst_5d": sig.inst_5d,
            }
            market_context = sig.ai_overall.get("market_context", {}) if isinstance(sig.ai_overall, dict) else {}
            program_context = sig.ai_overall.get("program_context", {}) if isinstance(sig.ai_overall, dict) else {}
            external_market_context = sig.ai_overall.get("external_market_context", {}) if isinstance(sig.ai_overall, dict) else {}
            intraday_context = sig.ai_overall.get("intraday_context", {}) if isinstance(sig.ai_overall, dict) else {}
            sector_context = sig.ai_overall.get("sector_leadership", {}) if isinstance(sig.ai_overall, dict) else {}
            intraday_pressure = sig.ai_overall.get("intraday_pressure", {}) if isinstance(sig.ai_overall, dict) else {}
            stock_program_context = sig.ai_overall.get("stock_program_context", {}) if isinstance(sig.ai_overall, dict) else {}
            news_attention = sig.ai_overall.get("news_attention", {}) if isinstance(sig.ai_overall, dict) else {}
            news_items = sig.news_items[:3] if isinstance(sig.news_items, list) else []
            if isinstance(market_context, dict) and market_context:
                metrics["market_context"] = market_context
            if isinstance(program_context, dict) and program_context:
                metrics["program_context"] = program_context
            if isinstance(external_market_context, dict) and external_market_context:
                metrics["external_market_context"] = external_market_context
            if isinstance(intraday_context, dict) and intraday_context:
                metrics["intraday_context"] = intraday_context
            if isinstance(sector_context, dict) and sector_context:
                metrics["sector_leadership"] = sector_context
            if isinstance(intraday_pressure, dict) and intraday_pressure:
                metrics["intraday_pressure"] = intraday_pressure
            if isinstance(stock_program_context, dict) and stock_program_context:
                metrics["stock_program_context"] = stock_program_context
            if isinstance(news_attention, dict) and news_attention:
                metrics["news_attention"] = news_attention
            metrics["fresh_news_count"] = len(news_items)
            metrics["news_window_label"] = str(sig.ai_overall.get("news_window_label", "") or "") if isinstance(sig.ai_overall, dict) else ""

            if id(sig) not in ai_target_ids:
                fallback = self.llm_analyzer.build_rule_based_overall(
                    stock_name=sig.stock_name,
                    rule_scores=rule_scores,
                    metrics=metrics,
                    news_items=news_items,
                    status="SKIPPED_TOP10",
                    reason=f"상위 {top_k}개만 AI 종합평가 대상으로 설정되어 규칙 기반 해설을 제공합니다.",
                )
                fallback["top_k_limit"] = top_k
                fallback["rank"] = idx + 1
                if isinstance(market_context, dict):
                    fallback["market_context"] = market_context
                if isinstance(program_context, dict):
                    fallback["program_context"] = program_context
                if isinstance(external_market_context, dict):
                    fallback["external_market_context"] = external_market_context
                if isinstance(intraday_context, dict):
                    fallback["intraday_context"] = intraday_context
                if isinstance(sector_context, dict):
                    fallback["sector_leadership"] = sector_context
                if isinstance(intraday_pressure, dict):
                    fallback["intraday_pressure"] = intraday_pressure
                if isinstance(stock_program_context, dict):
                    fallback["stock_program_context"] = stock_program_context
                if isinstance(news_attention, dict):
                    fallback["news_attention"] = news_attention
                fallback.setdefault("market_policy", metrics.get("market_policy", {}))
                fallback.setdefault("base_grade", metrics.get("base_grade", _grade_value(sig.grade)))
                sig.ai_overall = fallback
                continue

            print(f"    [LLM-OVERALL] {sig.stock_name} 종합평가... ({idx+1}/{top_k})")
            overall = await self.llm_analyzer.analyze_overall_decision(
                stock_name=sig.stock_name,
                rule_scores=rule_scores,
                metrics=metrics,
                news_items=news_items,
            )
            if isinstance(overall, dict):
                overall.setdefault("top_k_limit", top_k)
                overall.setdefault("rank", idx + 1)
                overall.setdefault("market_context", market_context if isinstance(market_context, dict) else {})
                overall.setdefault("program_context", program_context if isinstance(program_context, dict) else {})
                overall.setdefault("external_market_context", external_market_context if isinstance(external_market_context, dict) else {})
                overall.setdefault("intraday_context", intraday_context if isinstance(intraday_context, dict) else {})
                overall.setdefault("sector_leadership", sector_context if isinstance(sector_context, dict) else {})
                overall.setdefault("intraday_pressure", intraday_pressure if isinstance(intraday_pressure, dict) else {})
                overall.setdefault("stock_program_context", stock_program_context if isinstance(stock_program_context, dict) else {})
                overall.setdefault("news_attention", news_attention if isinstance(news_attention, dict) else {})
                overall.setdefault("market_policy", metrics.get("market_policy", {}))
                overall.setdefault("base_grade", metrics.get("base_grade", _grade_value(sig.grade)))
            sig.ai_overall = overall
    
    async def _analyze_stock(
        self,
        stock: StockData,
        target_date: date
    ) -> Optional[Signal]:
        """개별 종목 분석"""
        try:
            # 1. 상세 정보 조회 (이미 top_gainers에서 대부분 가져왔으나 52주 고가 등 보완)
            detail = await self._collector.get_stock_detail(stock.code)
            if detail:
                # 병합 로직 (필요한 정보만 업데이트)
                stock.high_52w = detail.high_52w
            
            # 2. 차트 데이터 조회
            charts = await self._collector.get_chart_data(stock.code, 60)
            
            # 3. 뉴스 조회 (본문 포함, 종목명 전달)
            # EnhancedNewsCollector: get_stock_news(code, limit, name)
            news_list = await self._news.get_stock_news(stock.code, 3, stock.name, target_date=target_date)
            print(f"    -> News fetched: {len(news_list)}")
            news_window_label = describe_news_window(
                target_date,
                cutoff_hour=int(getattr(self.config, "news_prev_day_cutoff_hour", 15) or 15),
                cutoff_minute=int(getattr(self.config, "news_prev_day_cutoff_minute", 30) or 30),
            )
            
            # 4. LLM 뉴스 분석 (Rate Limit 방지 Sleep)
            llm_result = None
            if news_list:
                if self.llm_analyzer.model:
                    if self._llm_calls < self.max_llm_calls:
                        self._llm_calls += 1
                        print(f"    [LLM] Analyzing {stock.name} news... ({self._llm_calls}/{self.max_llm_calls})")
                        news_dicts = [
                            {
                                "title": n.title,
                                "summary": n.summary,
                                "source": n.source,
                                "published_at": n.published_at.isoformat() if n.published_at else "",
                            }
                            for n in news_list
                        ]
                        llm_result = await self.llm_analyzer.analyze_news_sentiment(stock.name, news_dicts)
                        if llm_result:
                            print(f"      -> Score: {llm_result.get('score')}, Reason: {llm_result.get('reason')}")
                    else:
                        llm_result = {
                            "score": 1,
                            "reason": "일일 LLM 호출 한도 초과로 기본점수 1점을 적용했습니다.",
                            "status": "SKIPPED_LIMIT",
                            "provider": str(getattr(self.llm_analyzer, "provider", "off")),
                            "model": str(getattr(self.llm_analyzer, "model", "")),
                            "reasoning_effort": str(getattr(self.llm_analyzer, "reasoning_effort", "")),
                            "meta": {
                                "status": "SKIPPED_LIMIT",
                                "provider": str(getattr(self.llm_analyzer, "provider", "off")),
                                "model": str(getattr(self.llm_analyzer, "model", "")),
                                "reasoning_effort": str(getattr(self.llm_analyzer, "reasoning_effort", "")),
                            },
                        }
                else:
                    llm_result = {
                        "score": 1,
                        "reason": "AI 모델이 준비되지 않아 기본점수 1점을 적용했습니다.",
                        "status": "NO_MODEL",
                        "provider": str(getattr(self.llm_analyzer, "provider", "off")),
                        "model": str(getattr(self.llm_analyzer, "model", "")),
                        "reasoning_effort": str(getattr(self.llm_analyzer, "reasoning_effort", "")),
                        "meta": {
                            "status": "NO_MODEL",
                            "provider": str(getattr(self.llm_analyzer, "provider", "off")),
                            "model": str(getattr(self.llm_analyzer, "model", "")),
                            "reasoning_effort": str(getattr(self.llm_analyzer, "reasoning_effort", "")),
                        },
                    }

            # 5. 수급 데이터 조회 (CSV에서 로드, 5일 누적)
            supply = await self._collector.get_supply_data(stock.code)
            if supply:
                print(f"      -> Supply 5d: Foreign {supply.foreign_buy_5d}, Inst {supply.inst_buy_5d}")
            
            # 6. 점수 계산 (LLM 결과 반영)
            market_context = await self._collector.get_market_context(stock.market)
            program_trade = await self._collector.get_program_trade(stock.market)
            intraday_feature = await self._collector.get_intraday_feature(stock.code)
            stock_program = await self._collector.get_stock_program_data(stock.code)

            if intraday_feature.current_price > 0:
                stock.close = intraday_feature.current_price
            if intraday_feature.change_pct:
                stock.change_pct = intraday_feature.change_pct
            if intraday_feature.acc_trade_value > 0:
                stock.trading_value = intraday_feature.acc_trade_value
            if intraday_feature.acc_trade_volume > 0:
                stock.volume = intraday_feature.acc_trade_volume

            sector_leadership = (
                self._factor_context.sector_for_stock(stock.code, stock.sector)
                if self._factor_context is not None
                else None
            )
            intraday_pressure = (
                self._factor_context.intraday_for_stock(stock.code, stock.market, intraday_feature)
                if self._factor_context is not None
                else None
            )
            news_attention = (
                self._factor_context.news_attention_for_stock(
                    stock.code,
                    news_items=[
                        {
                            "title": n.title,
                            "summary": n.summary,
                            "source": n.source,
                            "published_at": n.published_at.isoformat() if n.published_at else "",
                        }
                        for n in news_list
                    ],
                    llm_meta=(llm_result.get("meta") if isinstance(llm_result, dict) and isinstance(llm_result.get("meta"), dict) else {}),
                )
                if self._factor_context is not None
                else None
            )
            if sector_leadership is not None and (not str(stock.sector or "").strip()):
                stock.sector = str(sector_leadership.sector_key or "General")

            score, checklist = self.scorer.calculate(
                stock,
                charts,
                news_list,
                supply,
                market_context,
                program_trade,
                stock_program,
                sector_leadership,
                intraday_pressure,
                news_attention,
                llm_result,
            )
            
            # 7. 등급 결정
            base_grade = self.scorer.determine_grade(stock, score)
            market_policy = apply_market_grade_policy(
                base_grade=base_grade.value,
                market_context=market_context.to_dict(),
                program_context=program_trade.to_dict(),
                external_market_context=self.external_market_context,
            )
            adjusted_grade = str(market_policy.get("adjusted_grade", "C") or "C")
            grade = Grade[adjusted_grade] if adjusted_grade in Grade.__members__ else Grade.C
            
            # 7. 포지션 계산
            position = self.position_sizer.calculate(stock.close, grade)
            
            # 8. 시그널 생성
            signal = Signal(
                stock_code=stock.code,
                stock_name=stock.name,
                market=stock.market,
                sector=stock.sector,
                signal_date=target_date,
                signal_time=datetime.now(SEOUL_TZ),
                grade=grade,
                score=score,
                checklist=checklist,
                news_items=[{
                    "title": n.title,
                    "summary": n.summary,
                    "source": n.source,
                    "published_at": n.published_at.isoformat() if n.published_at else "",
                    "url": n.url
                } for n in news_list[:5]], # 상위 5개 뉴스 저장
                ai_overall={
                    "market_context": market_context.to_dict(),
                    "program_context": program_trade.to_dict(),
                    "stock_program_context": stock_program.to_dict(),
                    "intraday_context": intraday_feature.to_dict(),
                    "external_market_context": dict(self.external_market_context),
                    "sector_leadership": sector_leadership.to_dict() if sector_leadership is not None else {},
                    "intraday_pressure": intraday_pressure.to_dict() if intraday_pressure is not None else {},
                    "news_attention": news_attention.to_dict() if news_attention is not None else {},
                    "market_policy": market_policy,
                    "base_grade": base_grade.value,
                    "news_window_label": news_window_label,
                    "fresh_news_count": len(news_list),
                },
                foreign_5d=int(getattr(supply, "foreign_buy_5d", 0) or 0),
                inst_5d=int(getattr(supply, "inst_buy_5d", 0) or 0),
                individual_5d=int(getattr(supply, "individual_buy_5d", 0) or 0),
                current_price=stock.close,
                entry_price=position.entry_price,
                stop_price=position.stop_price,
                target_price=position.target_price,
                r_value=position.r_value,
                position_size=position.position_size,
                quantity=position.quantity,
                r_multiplier=position.r_multiplier,
                trading_value=stock.trading_value,
                change_pct=stock.change_pct,
                status=SignalStatus.PENDING,
                created_at=datetime.now(),
            )
            
            return signal
            
        except Exception as e:
            print(f"    [ERROR] 분석 실패: {stock.name}({stock.code}) - {e}")
            print(traceback.format_exc(limit=1).strip())
            return None
    
    def get_summary(self, signals: List[Signal]) -> Dict:
        """시그널 요약 정보"""
        summary = {
            "total": len(signals),
            "by_grade": {g.value: 0 for g in Grade},
            "by_base_grade": {g.value: 0 for g in Grade},
            "by_market": {},
            "total_position": 0,
            "total_risk": 0,
            "market_adjusted_count": 0,
        }
        
        for s in signals:
            summary["by_grade"][s.grade.value] += 1
            base_grade = str(s.ai_overall.get("base_grade", s.grade.value) or s.grade.value)
            summary["by_base_grade"][base_grade] = summary["by_base_grade"].get(base_grade, 0) + 1
            summary["by_market"][s.market] = summary["by_market"].get(s.market, 0) + 1
            summary["total_position"] += s.position_size
            summary["total_risk"] += s.r_value * s.r_multiplier
            if base_grade != s.grade.value:
                summary["market_adjusted_count"] += 1
        
        return summary


async def run_screener(
    capital: float = 50_000_000,
    markets: List[str] = None,
) -> ScreenerResult:
    """
    스크리너 실행 (간편 함수)
    """
    start_time = time.time()
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    freshness_report = assert_data_ready_for_run(base_dir)
    effective_date = _reference_trade_date(freshness_report)
    
    runtime_meta: Dict[str, Any] = {}
    async with SignalGenerator(capital=capital) as generator:
        signals = await generator.generate(target_date=effective_date, markets=markets)
        summary = generator.get_summary(signals)
        runtime_meta = {
            "collector_source": str(os.getenv("COLLECTOR_SOURCE", "naver") or "naver"),
            "llm_provider": str(getattr(generator.llm_analyzer, "provider", "off")),
            "llm_model": str(getattr(generator.llm_analyzer, "model", "")),
            "llm_transport": str(getattr(generator.llm_analyzer, "_codex_transport", "")),
            "llm_ready": bool(getattr(generator.llm_analyzer, "is_ready", lambda: False)()),
            "reasoning_effort": str(getattr(generator.llm_analyzer, "reasoning_effort", "")),
            "llm_calls_used": int(getattr(generator, "_llm_calls", 0)),
            "llm_calls_limit": int(getattr(generator, "max_llm_calls", 0)),
            "overall_ai_top_k": int(getattr(generator, "max_overall_ai_calls", 0)),
            "freshness": freshness_report,
            "external_market_context": dict(getattr(generator, "external_market_context", {}) or {}),
            "score_total_max": TOTAL_RULE_SCORE_MAX,
            "by_base_grade": dict(summary.get("by_base_grade", {})),
            "market_adjusted_count": int(summary.get("market_adjusted_count", 0)),
            "effective_trade_date": effective_date.isoformat(),
        }
    
    processing_time = (time.time() - start_time) * 1000
    
    result = ScreenerResult(
        date=effective_date,
        total_candidates=summary["total"],
        filtered_count=len(signals),
        signals=signals,
        by_grade=summary["by_grade"],
        by_market=summary["by_market"],
        processing_time_ms=processing_time,
    )
    
    # 결과 저장
    save_result_to_json(result, runtime_meta=runtime_meta)
    
    return result

async def analyze_single_stock_by_code(
    code: str,
    capital: float = 50_000_000,
) -> Optional[Signal]:
    """
    단일 종목 분석 및 결과 JSON 업데이트
    """
    raw_code = str(code or "").strip()
    if (not raw_code) or (not raw_code.isdigit()) or (len(raw_code) > 6):
        return None
    code = raw_code.zfill(6)
    effective_date = date.today()

    async with SignalGenerator(capital=capital) as generator:
        generator.external_market_context = get_external_market_context()
        generator._factor_context = FactorContext(
            snapshot_df=generator._collector.snapshot_df if generator._collector else None,
            news_df=generator._news.news_df if generator._news else None,
            flows_df=generator._collector.flows_df if generator._collector else None,
            intraday_df=generator._collector.intraday_df if generator._collector else None,
            intraday_snapshots_df=generator._collector.intraday_snapshots_df if generator._collector else None,
            condition_hits_df=generator._collector.condition_hits_df if generator._collector else None,
            program_snapshots_df=generator._collector.program_snapshots_df if generator._collector else None,
            target_date=effective_date,
        )
        detail = await generator._collector.get_stock_detail(code)
        if not detail:
            print(f"Stock detail not found for {code}")
            return None

        stock = detail
        print(f"Re-analyzing {stock.name} ({stock.code})...")
        new_signal = await generator._analyze_stock(stock, effective_date)

        if new_signal:
            print(f"[OK] Re-analysis complete: {new_signal.grade.value} (Score: {new_signal.score.total})")

            if not is_supabase_backend():
                raise RuntimeError("DB backend required for analyze_single_stock_by_code")

            repo = SupabaseRepository.from_env()
            data = repo.load_run_payload("latest") or {
                "date": effective_date.isoformat(),
                "total_candidates": 0,
                "filtered_count": 0,
                "signals": [],
                "by_grade": {g.value: 0 for g in Grade},
                "by_market": {},
                "processing_time_ms": 0,
                "updated_at": datetime.now().isoformat(),
            }

            signals = data.get("signals", [])
            replaced = False
            for i, sig in enumerate(signals):
                if str(sig.get("stock_code", "")).zfill(6) == code.zfill(6):
                    signals[i] = new_signal.to_dict()
                    replaced = True
                    break

            if not replaced:
                signals.append(new_signal.to_dict())

            grade_order = {"S": 0, "A": 1, "B": 2, "C": 3}
            signals.sort(key=lambda s: (grade_order.get(s.get("grade", "C"), 9), -(s.get("score", {}).get("total", 0))))

            by_grade = {g.value: 0 for g in Grade}
            by_market: Dict[str, int] = {}
            for sig in signals:
                by_grade[sig.get("grade", "C")] = by_grade.get(sig.get("grade", "C"), 0) + 1
                m = sig.get("market", "UNKNOWN")
                by_market[m] = by_market.get(m, 0) + 1

            data["date"] = effective_date.isoformat()
            data["signals"] = signals
            data["filtered_count"] = len(signals)
            data["total_candidates"] = max(data.get("total_candidates", 0), len(signals))
            data["by_grade"] = by_grade
            data["by_market"] = by_market
            data["updated_at"] = datetime.now().isoformat()

            repo.save_screener_result(data)

            return new_signal

        else:
            print("Re-analysis failed or grade too low.")
            return None

def save_result_to_json(result: ScreenerResult, runtime_meta: Optional[Dict[str, Any]] = None):
    """결과를 DB(jongga_runs/jongga_signals)에 저장"""

    data = {
        "date": result.date.isoformat(),
        "total_candidates": result.total_candidates,
        "filtered_count": result.filtered_count,
        "signals": [s.to_dict() for s in result.signals],
        "by_grade": result.by_grade,
        "by_market": result.by_market,
        "runtime_meta": dict(runtime_meta or {}),
        "processing_time_ms": result.processing_time_ms,
        "updated_at": datetime.now().isoformat()
    }

    if not is_supabase_backend():
        raise RuntimeError("DB backend is required for save_result_to_json")
    repo = SupabaseRepository.from_env()
    repo.save_screener_result(data)
    print("[저장 완료] Supabase: jongga_runs/jongga_signals")


# 테스트용 메인
async def main():
    """테스트 실행"""
    print("=" * 60)
    print("종가베팅 시그널 생성기 v2 (Live Entity)")
    print("=" * 60)
    
    capital = 50_000_000
    print(f"\n자본금: {capital:,}원")
    print(f"R값: {capital * 0.005:,.0f}원 (0.5%)")
    
    result = await run_screener(capital=capital)
    
    print(f"\n처리 시간: {result.processing_time_ms:.0f}ms")
    print(f"생성된 시그널: {len(result.signals)}개")
    print(f"등급별: {result.by_grade}")
    
    print("\n" + "=" * 60)
    print("시그널 상세")
    print("=" * 60)
    
    for i, signal in enumerate(result.signals, 1):
        print(f"\n[{i}] {signal.stock_name} ({signal.stock_code})")
        print(f"    등급: {signal.grade.value}")
        print(f"    점수: {signal.score.total}/{TOTAL_RULE_SCORE_MAX} (뉴스:{signal.score.news}, 수급:{signal.score.supply}, 차트:{signal.score.chart})")
        print(f"    등락률: {signal.change_pct:+.2f}%")
        print(f"    거래대금: {signal.trading_value / 100_000_000:,.0f}억")
        print(f"    진입가: {signal.entry_price:,}원")
        print(f"    손절가: {signal.stop_price:,}원 (-3%)")
        print(f"    목표가: {signal.target_price:,}원 (+5%)")
        print(f"    수량: {signal.quantity:,}주")
        print(f"    포지션: {signal.position_size:,.0f}원")
        
        # 체크리스트 출력
        print("    [체크리스트]")
        check = signal.checklist
        print(f"     - 뉴스: {'O' if check.has_news else 'X'} {check.news_sources}")
        print(f"     - 신고가/돌파: {'O' if check.is_new_high or check.is_breakout else 'X'}")
        print(f"     - 수급: {'O' if check.supply_positive else 'X'}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n중단됨")

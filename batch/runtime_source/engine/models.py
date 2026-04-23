from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List

from engine.config import Grade


class SignalStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass
class StockData:
    code: str
    name: str
    market: str
    sector: str
    close: float
    change_pct: float
    trading_value: int
    volume: int
    marcap: int
    high_52w: float = 0.0


@dataclass
class ChartData:
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class NewsItem:
    title: str
    summary: str
    source: str
    published_at: datetime | None = None
    url: str = ""


@dataclass
class SupplyData:
    foreign_buy_5d: int = 0
    inst_buy_5d: int = 0
    individual_buy_5d: int = 0
    # Design Ref: Design §5 Module B — 수급 연속성(수급단타왕 매일매일 매집)
    # N일 연속 순매수 카운트. 파이프라인에서 채워지지 않으면 0 (기존 동작 유지)
    continuity_days_foreign: int = 0
    continuity_days_institution: int = 0


@dataclass
class MarketContextData:
    market: str
    market_label: str = ""
    trade_date: date | None = None
    snapshot_time: datetime | None = None
    market_status: str = ""
    index_value: float = 0.0
    change_pct: float = 0.0
    rise_count: int = 0
    steady_count: int = 0
    fall_count: int = 0
    upper_count: int = 0
    lower_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "market_label": self.market_label,
            "trade_date": self.trade_date.isoformat() if isinstance(self.trade_date, date) else "",
            "snapshot_time": self.snapshot_time.isoformat() if isinstance(self.snapshot_time, datetime) else "",
            "market_status": self.market_status,
            "index_value": self.index_value,
            "change_pct": self.change_pct,
            "rise_count": self.rise_count,
            "steady_count": self.steady_count,
            "fall_count": self.fall_count,
            "upper_count": self.upper_count,
            "lower_count": self.lower_count,
        }


@dataclass
class ProgramTradeData:
    market: str
    trade_date: date | None = None
    snapshot_time: datetime | None = None
    market_status: str = ""
    arbitrage_buy: int = 0
    arbitrage_sell: int = 0
    arbitrage_net: int = 0
    non_arbitrage_buy: int = 0
    non_arbitrage_sell: int = 0
    non_arbitrage_net: int = 0
    total_buy: int = 0
    total_sell: int = 0
    total_net: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "trade_date": self.trade_date.isoformat() if isinstance(self.trade_date, date) else "",
            "snapshot_time": self.snapshot_time.isoformat() if isinstance(self.snapshot_time, datetime) else "",
            "market_status": self.market_status,
            "arbitrage_buy": self.arbitrage_buy,
            "arbitrage_sell": self.arbitrage_sell,
            "arbitrage_net": self.arbitrage_net,
            "non_arbitrage_buy": self.non_arbitrage_buy,
            "non_arbitrage_sell": self.non_arbitrage_sell,
            "non_arbitrage_net": self.non_arbitrage_net,
            "total_buy": self.total_buy,
            "total_sell": self.total_sell,
            "total_net": self.total_net,
        }


@dataclass
class StockProgramData:
    ticker: str
    venue: str = ""
    latest_time: datetime | None = None
    current_price: float = 0.0
    change_pct: float = 0.0
    latest_net_buy_amt: int = 0
    latest_net_buy_qty: int = 0
    delta_10m_amt: int = 0
    delta_30m_amt: int = 0
    delta_10m_qty: int = 0
    delta_30m_qty: int = 0
    daily_net_buy_amt_5d: int = 0
    daily_net_buy_qty_5d: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "venue": self.venue,
            "latest_time": self.latest_time.isoformat() if isinstance(self.latest_time, datetime) else "",
            "current_price": self.current_price,
            "change_pct": self.change_pct,
            "latest_net_buy_amt": self.latest_net_buy_amt,
            "latest_net_buy_qty": self.latest_net_buy_qty,
            "delta_10m_amt": self.delta_10m_amt,
            "delta_30m_amt": self.delta_30m_amt,
            "delta_10m_qty": self.delta_10m_qty,
            "delta_30m_qty": self.delta_30m_qty,
            "daily_net_buy_amt_5d": self.daily_net_buy_amt_5d,
            "daily_net_buy_qty_5d": self.daily_net_buy_qty_5d,
        }


@dataclass
class IntradayFeatureData:
    ticker: str
    venue: str = ""
    current_price: float = 0.0
    change_pct: float = 0.0
    bid_total: int = 0
    ask_total: int = 0
    orderbook_imbalance: float = 0.0
    execution_strength: float = 0.0
    tick_volume: int = 0
    minute_pattern: str = ""
    minute_breakout_score: float = 0.0
    volume_surge_ratio: float = 0.0
    orderbook_surge_ratio: float = 0.0
    vi_active: bool = False
    vi_type: str = ""
    condition_hit_count: int = 0
    condition_names: list[str] = field(default_factory=list)
    acc_trade_value: int = 0
    acc_trade_volume: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "venue": self.venue,
            "current_price": self.current_price,
            "change_pct": self.change_pct,
            "bid_total": self.bid_total,
            "ask_total": self.ask_total,
            "orderbook_imbalance": self.orderbook_imbalance,
            "execution_strength": self.execution_strength,
            "tick_volume": self.tick_volume,
            "minute_pattern": self.minute_pattern,
            "minute_breakout_score": self.minute_breakout_score,
            "volume_surge_ratio": self.volume_surge_ratio,
            "orderbook_surge_ratio": self.orderbook_surge_ratio,
            "vi_active": self.vi_active,
            "vi_type": self.vi_type,
            "condition_hit_count": self.condition_hit_count,
            "condition_names": self.condition_names,
            "acc_trade_value": self.acc_trade_value,
            "acc_trade_volume": self.acc_trade_volume,
        }


@dataclass
class SectorLeadershipData:
    sector_key: str = ""
    sector_score: float = 0.0
    sector_rank: int = 999
    sector_count: int = 0
    sector_avg_change_pct: float = 0.0
    sector_total_trading_value: int = 0
    leader_rank: int = 999
    leader_score: float = 0.0
    is_leader: bool = False
    top_ticker: str = ""
    top_stock_name: str = ""
    sector_news_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector_key": self.sector_key,
            "sector_score": self.sector_score,
            "sector_rank": self.sector_rank,
            "sector_count": self.sector_count,
            "sector_avg_change_pct": self.sector_avg_change_pct,
            "sector_total_trading_value": self.sector_total_trading_value,
            "leader_rank": self.leader_rank,
            "leader_score": self.leader_score,
            "is_leader": self.is_leader,
            "top_ticker": self.top_ticker,
            "top_stock_name": self.top_stock_name,
            "sector_news_count": self.sector_news_count,
        }


@dataclass
class IntradayPressureData:
    score: float = 0.0
    pressure_status: str = "NEUTRAL"
    execution_strength: float = 0.0
    execution_delta: float = 0.0
    orderbook_imbalance: float = 0.0
    orderbook_delta: float = 0.0
    minute_pattern: str = ""
    minute_breakout_score: float = 0.0
    volume_surge_ratio: float = 0.0
    orderbook_surge_ratio: float = 0.0
    condition_hit_count: int = 0
    program_delta: int = 0
    snapshot_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "pressure_status": self.pressure_status,
            "execution_strength": self.execution_strength,
            "execution_delta": self.execution_delta,
            "orderbook_imbalance": self.orderbook_imbalance,
            "orderbook_delta": self.orderbook_delta,
            "minute_pattern": self.minute_pattern,
            "minute_breakout_score": self.minute_breakout_score,
            "volume_surge_ratio": self.volume_surge_ratio,
            "orderbook_surge_ratio": self.orderbook_surge_ratio,
            "condition_hit_count": self.condition_hit_count,
            "program_delta": self.program_delta,
            "snapshot_count": self.snapshot_count,
        }


@dataclass
class NewsAttentionData:
    material_strength: float = 0.0
    attention_score: float = 0.0
    novelty_score: float = 0.0
    entity_confidence: float = 0.0
    media_count: int = 0
    article_count: int = 0
    strong_broadcast: bool = False
    category: str = ""
    tone: str = ""
    freshness_minutes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "material_strength": self.material_strength,
            "attention_score": self.attention_score,
            "novelty_score": self.novelty_score,
            "entity_confidence": self.entity_confidence,
            "media_count": self.media_count,
            "article_count": self.article_count,
            "strong_broadcast": self.strong_broadcast,
            "category": self.category,
            "tone": self.tone,
            "freshness_minutes": self.freshness_minutes,
        }


@dataclass
class ScoreDetail:
    news: int = 0
    volume: int = 0
    chart: int = 0
    candle: int = 0
    consolidation: int = 0
    supply: int = 0
    market: int = 0
    program: int = 0
    stock_program: int = 0
    sector: int = 0
    leader: int = 0
    intraday: int = 0
    news_attention: int = 0
    # Design Ref: Design §5 Module B — 수급 연속성 보너스 (최대 1점), 실체성 뉴스 카운트
    supply_continuity: int = 0
    material_news_count: int = 0
    llm_reason: str = ""
    llm_meta: Dict[str, Any] = field(default_factory=dict)
    total: int = 0

    def finalize(self) -> "ScoreDetail":
        self.total = int(
            self.news
            + self.volume
            + self.chart
            + self.candle
            + self.consolidation
            + self.supply
            + self.supply_continuity
            + self.market
            + self.program
            + self.stock_program
            + self.sector
            + self.leader
            + self.intraday
            + self.news_attention
        )
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "news": self.news,
            "volume": self.volume,
            "chart": self.chart,
            "candle": self.candle,
            "consolidation": self.consolidation,
            "supply": self.supply,
            "market": self.market,
            "program": self.program,
            "stock_program": self.stock_program,
            "sector": self.sector,
            "leader": self.leader,
            "intraday": self.intraday,
            "news_attention": self.news_attention,
            "llm_reason": self.llm_reason,
            "llm_meta": self.llm_meta,
            "total": self.total,
        }


@dataclass
class ChecklistDetail:
    has_news: bool = False
    news_sources: List[str] = field(default_factory=list)
    is_new_high: bool = False
    is_breakout: bool = False
    supply_positive: bool = False
    volume_surge: bool = False
    market_supportive: bool = False
    program_supportive: bool = False
    stock_program_supportive: bool = False
    sector_supportive: bool = False
    leader_confirmed: bool = False
    intraday_supportive: bool = False
    news_attention_high: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_news": self.has_news,
            "news_sources": self.news_sources,
            "is_new_high": self.is_new_high,
            "is_breakout": self.is_breakout,
            "supply_positive": self.supply_positive,
            "volume_surge": self.volume_surge,
            "market_supportive": self.market_supportive,
            "program_supportive": self.program_supportive,
            "stock_program_supportive": self.stock_program_supportive,
            "sector_supportive": self.sector_supportive,
            "leader_confirmed": self.leader_confirmed,
            "intraday_supportive": self.intraday_supportive,
            "news_attention_high": self.news_attention_high,
        }


@dataclass
class Signal:
    stock_code: str
    stock_name: str
    market: str
    sector: str
    signal_date: date
    signal_time: datetime
    grade: Grade
    score: ScoreDetail
    checklist: ChecklistDetail
    news_items: List[Dict[str, Any]] = field(default_factory=list)
    ai_overall: Dict[str, Any] = field(default_factory=dict)
    foreign_5d: int = 0
    inst_5d: int = 0
    individual_5d: int = 0
    current_price: float = 0.0
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    r_value: float = 0.0
    position_size: float = 0.0
    quantity: int = 0
    r_multiplier: float = 0.0
    trading_value: int = 0
    change_pct: float = 0.0
    status: SignalStatus = SignalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "market": self.market,
            "sector": self.sector,
            "signal_date": self.signal_date.isoformat(),
            "signal_time": self.signal_time.isoformat(),
            "grade": self.grade.value if isinstance(self.grade, Grade) else str(self.grade),
            "score": self.score.to_dict(),
            "checklist": self.checklist.to_dict(),
            "news_items": self.news_items,
            "ai_overall": self.ai_overall,
            "foreign_5d": self.foreign_5d,
            "inst_5d": self.inst_5d,
            "individual_5d": self.individual_5d,
            "current_price": self.current_price,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "r_value": self.r_value,
            "position_size": self.position_size,
            "quantity": self.quantity,
            "r_multiplier": self.r_multiplier,
            "trading_value": self.trading_value,
            "change_pct": self.change_pct,
            "status": self.status.value if isinstance(self.status, SignalStatus) else str(self.status),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ScreenerResult:
    date: date
    total_candidates: int
    filtered_count: int
    signals: List[Signal]
    by_grade: Dict[str, int]
    by_market: Dict[str, int]
    processing_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "total_candidates": self.total_candidates,
            "filtered_count": self.filtered_count,
            "signals": [s.to_dict() for s in self.signals],
            "by_grade": self.by_grade,
            "by_market": self.by_market,
            "processing_time_ms": self.processing_time_ms,
            "updated_at": datetime.now().isoformat(),
        }

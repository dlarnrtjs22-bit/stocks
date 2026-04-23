# Design: NXT 종가배팅 v3 - Pragmatic Balance Architecture

작성일: 2026-04-22
작성자: 운영자
Plan 참조: `docs/01-plan/features/nxt-closing-bet-v2.plan.md`
선택 아키텍처: **Option C — Pragmatic Balance**

---

## Context Anchor (Plan 승계)

| 축 | 내용 |
|----|------|
| **WHY** | 15-16시 수동 매수의 타이밍 산포 제거 + NXT 장후 4시간 정보(뉴스/수급/미국선물)를 반영한 진짜 종가 매매 + 매일 자동 반복으로 재현성 확보 |
| **WHO** | 운영자 1인(kill switch/리포트 확인만). 모든 주문 자동 |
| **RISK** | 자동주문 오체결/중복, NXT 지정가only 유동성 미체결, 장후 정보 갭, 200만 예수금 제약, 배치 느림, 데몬 SPOF |
| **SUCCESS** | 15:30 자동추출 → 19:30/19:40 재평가 → 19:50~19:58 자동매수 → 익일 08:00~08:50 자동매도. kill switch+일일-5%+paper mode 안전망. 배치 90s 이내 |
| **SCOPE** | 엔진 점수 확장 / APScheduler 데몬 / kiwoom_order+trade_executor / SSE / asyncio 배치 재작성 / guards.py |

---

## 1. Overview

Plan v3의 8개 Phase(A~H)를 **APScheduler 단일 데몬 + 분리된 실행 모듈 + SSE 실시간 UI**로 통합 구현한다. 신규 인프라(Redis, Temporal, Prefect 등)는 도입하지 않고, systemd로 데몬 수명만 관리한다.

### 1.1 System Topology

```
 ┌─────────────────────────────────────────────────────────────┐
 │  systemd unit: stocks-scheduler.service (Restart=always)     │
 │  ┌────────────────────────────────────────────────────────┐  │
 │  │ scheduler.py  (APScheduler BlockingScheduler)           │  │
 │  │  ├─ cron 15:30  daily_candidate_extract()               │  │
 │  │  ├─ cron 19:30  post_close_briefing()                   │  │
 │  │  ├─ cron 19:40  post_close_briefing()                   │  │
 │  │  ├─ cron 19:50  trade_executor.buy(tranche=1, 40%)      │  │
 │  │  ├─ cron 19:54  trade_executor.buy(tranche=2, 30%)      │  │
 │  │  ├─ cron 19:58  trade_executor.buy(tranche=3, 30%)      │  │
 │  │  ├─ cron 08:00  trade_executor.sell_start()             │  │
 │  │  ├─ cron 08:02  trade_executor.sell_step(-1%)           │  │
 │  │  ├─ cron 08:04  trade_executor.sell_step(-2%)           │  │
 │  │  ├─ cron 08:05  trade_executor.sell_taker()             │  │
 │  │  ├─ interval 08:06-08:49 @1min  sell_chase()            │  │
 │  │  ├─ cron 08:50  sell_handover_to_krx()                  │  │
 │  │  ├─ cron 09:00:30  sell_market_ioc_final()              │  │
 │  │  ├─ cron 09:10  daily_pnl_reconcile() + kill_switch_eval│  │
 │  │  └─ cron Mon 06:00  refresh_nxt_tickers()               │  │
 │  └────────────────────────────────────────────────────────┘  │
 │                         │                                     │
 │                         ▼                                     │
 │  ┌────────────────────────────────────────────────────────┐  │
 │  │ guards.py (every job calls check_allowed() first)      │  │
 │  │  ├─ kill_switch_file_check()                           │  │
 │  │  ├─ daily_loss_limit_check()                           │  │
 │  │  ├─ paper_mode_check()                                 │  │
 │  │  └─ api_health_check()                                 │  │
 │  └────────────────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────┘
          │                          │                    │
          ▼                          ▼                    ▼
  ┌──────────────┐           ┌──────────────┐     ┌────────────┐
  │ PostgreSQL   │           │ Kiwoom API   │     │ Slack Bot  │
  │ (candidates, │           │ REST + WS    │     │  (alerts)  │
  │  orders,     │           └──────────────┘     └────────────┘
  │  briefing,   │
  │  pnl)        │
  └──────────────┘
          │
          ▼
  ┌──────────────────────────────────────────┐
  │  FastAPI (uvicorn, 포트 5056)             │
  │  ├─ /api/closing-bet/candidates  GET     │
  │  ├─ /api/closing-bet/briefing    GET     │
  │  ├─ /api/closing-bet/stream      SSE     │ ◄── UI EventSource
  │  ├─ /api/orders                  GET     │
  │  └─ /api/controls/killswitch     POST    │
  └──────────────────────────────────────────┘
          │
          ▼
  ┌──────────────────────────────────────────┐
  │  React Vite (기존 frontend/)              │
  │  ├─ CandidateTop2View (SSE subscribed)   │
  │  ├─ BriefingBadges                       │
  │  ├─ OrderTimeline                        │
  │  └─ KillSwitchPanel                      │
  └──────────────────────────────────────────┘
```

### 1.2 기존 코드와의 관계

- **엔진 재사용**: `batch/runtime_source/engine/{generator,scorer,decision_policy,position_sizer}.py` 기본 로직 유지, Phase B에서 필드 확장.
- **키움 클라이언트 재사용**: `batch/runtime_source/providers/kiwoom_client.py`의 `KiwoomRESTClient` 그대로 사용. `effective_venue` 로직은 **08:00~20:00 NXT 풀레인지**로 확장 (§5.1).
- **신규 모듈**:
  - `batch/runtime_source/scheduler.py` — APScheduler 데몬 (신규)
  - `batch/runtime_source/providers/kiwoom_order.py` — 주문 저수준 래퍼 (신규)
  - `batch/runtime_source/executor/trade_executor.py` — 주문 상태기계 (신규)
  - `batch/runtime_source/executor/guards.py` — 안전장치 (신규)
  - `batch/runtime_source/pipelines/post_close_briefing.py` — 19:30/19:40 브리핑 (신규)
  - `batch/runtime_source/pipelines/daily_candidate_extract.py` — 15:30 추출 (신규, 기존 생성기 호출)
  - `backend/app/routes/sse.py` — SSE 엔드포인트 (신규)
  - `frontend/src/hooks/useCandidateStream.ts` — SSE 구독 훅 (신규)

---

## 2. 모듈 구조 및 의존성

### 2.1 레이어

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: UI (React)                                         │
│  - CandidateTop2View, BriefingBadges, KillSwitchPanel       │
└─────────────────────────────────────────────────────────────┘
                         ▲ SSE
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: API (FastAPI)                                      │
│  - sse.py (EventSource stream)                               │
│  - closing_bet_service.py (확장: nxt_eligible + top2)       │
│  - order_service.py (신규: 주문 이력 조회)                   │
└─────────────────────────────────────────────────────────────┘
                         ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Scheduler + Executor                               │
│  - scheduler.py (APScheduler)                                │
│  - trade_executor.py (주문 상태기계, tranche 관리)          │
│  - guards.py (kill switch, P/L, paper mode)                  │
└─────────────────────────────────────────────────────────────┘
                         ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Pipelines                                          │
│  - daily_candidate_extract.py (15:30)                        │
│  - post_close_briefing.py (19:30/19:40)                      │
│  - daily_pnl_reconcile.py (09:10)                            │
│  - refresh_nxt_tickers.py (월 06:00)                         │
└─────────────────────────────────────────────────────────────┘
                         ▲
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Engine + Providers (기존)                          │
│  - engine/{generator,scorer,decision_policy,position_sizer} │
│  - providers/kiwoom_client.py                                │
│  - providers/kiwoom_order.py (신규)                          │
│  - supabase_py/repository.py                                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Phase별 파일 매트릭스

| Phase | 신규 파일 | 수정 파일 | 삭제 파일 |
|-------|---------|----------|----------|
| A. NXT 인프라 | `data/nxt_tickers.csv`, `batch/scripts/refresh_nxt_tickers.py`, `backend/app/services/nxt_lookup.py` | `backend/app/schemas/closing_bet.py`, `backend/app/services/closing_bet_service.py`, `frontend/src/components/closing-bet/FeaturedCard.tsx` | — |
| B. 수급단타왕 | — | `engine/scorer.py`, `engine/decision_policy.py`, `engine/position_sizer.py`, `engine/config.py`, `engine/models.py` (supply 필드 확장) | — |
| C. 15:30 배치 + Top 2 | `pipelines/daily_candidate_extract.py`, `db/migrations/V2__candidate_set_v3.sql` | `backend/app/services/pick_selector.py` (`select_top_2_sector_diverse`) | — |
| D. 19:30 브리핑 | `pipelines/post_close_briefing.py`, `providers/us_futures_client.py`, `db/migrations/V3__briefing.sql`, `backend/app/routes/briefing.py`, `backend/app/routes/sse.py`, `frontend/src/hooks/useCandidateStream.ts`, `frontend/src/components/closing-bet/BriefingBadges.tsx` | `frontend/src/components/closing-bet/FeaturedCard.tsx` (실시간 업데이트) | — |
| E. 자동매수 | `providers/kiwoom_order.py`, `executor/trade_executor.py`, `db/migrations/V4__orders.sql` | — | — |
| F. 자동매도 | `executor/sell_scheduler.py` (trade_executor의 매도 플로우) | `executor/trade_executor.py` | — |
| G. 안전장치 | `executor/guards.py`, `executor/alerts.py`, `.bkit/state/auto_trade_enabled` | `scheduler.py` (모든 job 시작 시 guards 호출) | — |
| H. 배치 재작성 | `providers/kiwoom_client_async.py` (asyncio 래퍼), `providers/cache.py` (TTL 딕셔너리) | `pipelines/kiwoom_bootstrap_collect.py`, `batch/runtime_source/engine/collectors.py`, `frontend/src/components/settings/DataSourceSettings.tsx` (라디오 제거) | 네이버 단독 파이프라인 (뉴스 fallback만 남김) |

---

## 3. Data Model (DDL 스케치)

### 3.1 신규 테이블

```sql
-- V1__nxt_tickers.sql (Phase A)
CREATE TABLE IF NOT EXISTS nxt_tickers (
    stock_code       VARCHAR(12) PRIMARY KEY,
    market           VARCHAR(16) NOT NULL,          -- KOSPI / KOSDAQ
    nxt_symbol       VARCHAR(16) NOT NULL,          -- _NX 접미사 포함
    tier             INT DEFAULT 1,                 -- 1=풀서비스, 0=축소
    first_seen_at    TIMESTAMPTZ DEFAULT now(),
    last_updated_at  TIMESTAMPTZ DEFAULT now(),
    source_rev       VARCHAR(32)                    -- nextrade.co.kr 리스트 리비전
);

-- V2__candidate_set_v3.sql (Phase C)
CREATE TABLE IF NOT EXISTS candidate_set_v3 (
    set_date         DATE        NOT NULL,
    rank             INT         NOT NULL,          -- 1 또는 2
    stock_code       VARCHAR(12) NOT NULL,
    stock_name       VARCHAR(64) NOT NULL,
    sector           VARCHAR(64),
    score_total      INT,
    base_grade       VARCHAR(2),
    final_grade      VARCHAR(2),
    change_pct       NUMERIC(6,2),
    trading_value    BIGINT,
    entry_price_hint NUMERIC(12,2),
    snapshot_json    JSONB,                         -- 그 시점 종목 스냅샷 전체
    created_at       TIMESTAMPTZ DEFAULT now(),
    replaced_from    VARCHAR(12),                   -- 교체 시 원래 종목
    replaced_reason  TEXT,
    PRIMARY KEY (set_date, rank, created_at)
);

-- V3__briefing.sql (Phase D)
CREATE TABLE IF NOT EXISTS post_close_briefing (
    brief_date       DATE        NOT NULL,
    brief_time       TIMESTAMPTZ NOT NULL,
    stock_code       VARCHAR(12) NOT NULL,
    news_status      VARCHAR(24),                   -- OK / DETERIORATED / MISSING
    material_delta   NUMERIC(5,2),
    liquidity_status VARCHAR(24),                   -- OK / THIN / UNAVAILABLE
    liquidity_score  NUMERIC(8,2),
    price_krx_close  NUMERIC(12,2),
    price_nxt_now    NUMERIC(12,2),
    divergence_pct   NUMERIC(6,3),
    divergence_warn  BOOLEAN,
    us_es_chg_pct    NUMERIC(6,3),
    us_nq_chg_pct    NUMERIC(6,3),
    us_risk_off      BOOLEAN,
    action           VARCHAR(24),                   -- KEEP / REPLACE / DROP / QTY_HALF
    payload          JSONB,
    PRIMARY KEY (brief_date, brief_time, stock_code)
);

-- V4__orders.sql (Phase E/F)
CREATE TABLE IF NOT EXISTS auto_orders (
    order_id         VARCHAR(32) PRIMARY KEY,       -- 키움 order_id
    idempotency_key  VARCHAR(64) UNIQUE NOT NULL,   -- {date}_{ticker}_{side}_{tranche}_{ts}
    set_date         DATE        NOT NULL,
    stock_code       VARCHAR(12) NOT NULL,
    side             VARCHAR(4)  NOT NULL,          -- BUY / SELL
    tranche          VARCHAR(16) NOT NULL,          -- T1 / T2 / T3 / S1 / S2 / ...
    venue            VARCHAR(8)  NOT NULL,          -- NXT / KRX
    order_type       VARCHAR(16) NOT NULL,          -- LIMIT / LIMIT_MAKER / LIMIT_TAKER / MARKET_IOC
    price            NUMERIC(12,2) NOT NULL,
    qty              INT NOT NULL,
    status           VARCHAR(16) NOT NULL,          -- PENDING / FILLED / PARTIAL / CANCELLED / FAILED
    filled_qty       INT DEFAULT 0,
    filled_avg_price NUMERIC(12,2),
    requested_at     TIMESTAMPTZ NOT NULL,
    filled_at        TIMESTAMPTZ,
    error_code       VARCHAR(32),
    error_msg        TEXT,
    paper_mode       BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_auto_orders_date_ticker ON auto_orders(set_date, stock_code);
CREATE INDEX idx_auto_orders_status ON auto_orders(status);

-- V5__pnl.sql (Phase G)
CREATE TABLE IF NOT EXISTS daily_pnl (
    pnl_date         DATE PRIMARY KEY,
    gross_buy_krw    BIGINT DEFAULT 0,
    gross_sell_krw   BIGINT DEFAULT 0,
    realized_pnl_krw BIGINT DEFAULT 0,
    realized_pct     NUMERIC(6,3),
    fee_krw          BIGINT DEFAULT 0,
    positions_open   INT DEFAULT 0,
    cumulative_pct   NUMERIC(6,3),                  -- 누적 대비 예수금 %
    kill_switch_hit  BOOLEAN DEFAULT FALSE,
    updated_at       TIMESTAMPTZ DEFAULT now()
);
```

### 3.2 기존 테이블 확장

- `stock_meta` (또는 상응 테이블) 에 `nxt_eligible BOOLEAN` 컬럼 추가 (nxt_tickers JOIN으로도 가능, 조회 편의로 캐시)
- 기존 `signals` 테이블의 row에 `material_news_count INT`, `continuity_days_foreign INT`, `continuity_days_institution INT` 3개 컬럼 추가 (Phase B)

---

## 4. API Contracts

### 4.1 REST (기존 확장 + 신규)

```typescript
// GET /api/closing-bet (기존, 응답 스키마 확장)
interface ClosingBetItem {
  // ... 기존 필드
  nxt_eligible: boolean;                    // 신규 (Phase A)
  recommended_window: "19:40-19:55" | "15:22-15:28" | null;
  recommended_order_type: "LIMIT_MAKER" | "LIMIT" | "LIMIT_TAKER";
  continuity_foreign_days: number;          // 신규 (Phase B)
  continuity_inst_days: number;             // 신규 (Phase B)
  material_news_count: number;              // 신규 (Phase B)
}

// GET /api/closing-bet/candidates?date=YYYY-MM-DD (신규 Phase C)
interface CandidateSetResponse {
  date: string;
  created_at: string;
  candidates: CandidateTop2Item[];          // 최대 2
  replacement_history: ReplacementEvent[];
}
interface CandidateTop2Item {
  rank: 1 | 2;
  stock_code: string;
  stock_name: string;
  sector: string;
  score_total: number;
  grade: "S" | "A" | "B";
  nxt_eligible: true;                       // top2는 항상 true
  // ...
}

// GET /api/closing-bet/briefing?date=YYYY-MM-DD (신규 Phase D)
interface BriefingResponse {
  briefings: Briefing[];                     // 19:30, 19:40 시점별
}
interface Briefing {
  brief_time: string;
  stocks: BriefingPerStock[];
  us_es_chg_pct: number;
  us_nq_chg_pct: number;
  us_risk_off: boolean;
}

// GET /api/closing-bet/stream  (신규 Phase D, SSE)
// Event-Stream: text/event-stream
// Events:
//   - candidate.updated { rank, stock_code, ... }
//   - candidate.replaced { from, to, reason }
//   - briefing.added { brief_time, payload }
//   - order.placed / order.filled / order.failed

// GET /api/orders?date=YYYY-MM-DD (신규 Phase E)
interface OrderListResponse {
  orders: AutoOrder[];
}

// POST /api/controls/killswitch (신규 Phase G)
interface KillSwitchRequest { enabled: boolean; reason?: string; }
interface KillSwitchResponse { enabled: boolean; updated_at: string; }
```

### 4.2 SSE 구조

```
event: candidate.replaced
data: {"from":"005930","to":"000660","reason":"score_delta_12pct","at":"2026-04-23T19:40:03+09:00"}

event: briefing.added
data: {"brief_time":"2026-04-23T19:30:00+09:00", ...}

event: order.placed
data: {"order_id":"KW-...", "stock_code":"...", "tranche":"T1", "price":72000, "qty":10}
```

### 4.3 키움 주문 API 래핑 (`kiwoom_order.py` 공개 함수)

```python
def place_limit_order(
    ticker: str,
    side: Literal["BUY", "SELL"],
    qty: int,
    price: int,
    venue: Literal["NXT", "KRX"],
    idempotency_key: str,
) -> KiwoomOrderResult: ...

def cancel_order(order_id: str) -> bool: ...

def get_order_status(order_id: str) -> OrderStatus: ...

def get_quote_snapshot(ticker: str, venue: str) -> QuoteSnapshot: ...
#  QuoteSnapshot: bid1, ask1, last, bid_qty, ask_qty, ts

def get_deposit() -> int: ...                       # 현재 예수금 (원)

def stream_fill_events(order_ids: list[str]) -> AsyncIterator[FillEvent]: ...
#  WebSocket 구독으로 체결 이벤트 실시간 수신
```

---

## 5. 핵심 로직 상세

### 5.1 `effective_venue` 확장 (08:00~20:00 NXT 인식)

현재는 15:40 이후만 NXT로 인식. 자동 루프에서는 아래처럼 확장.

```python
def effective_venue(now_epoch: float | None = None) -> tuple[str, str]:
    ts = time.localtime(now_epoch or time.time())
    hhmm = ts.tm_hour * 100 + ts.tm_min
    # NXT 프리마켓
    if 800 <= hhmm < 850:
        return "NXT_PRE", "2"
    # KRX + NXT 메인 공존 (정책: NXT 선호, 유동성 부족 시 KRX)
    if 900 <= hhmm < 1520:
        return "KRX", "1"   # 메인 수집은 KRX (NXT도 가능하나 일관성)
    # KRX 동시호가
    if 1520 <= hhmm < 1530:
        return "KRX", "1"
    # NXT 애프터마켓
    if 1530 <= hhmm < 2000:
        return "NXT", "2"
    # 장외 — 마지막 수집 데이터 재사용
    return "KRX", "1"
```

### 5.2 Top 2 섹터 다양성 선정 (Phase C)

```python
def select_top_2_sector_diverse(
    rows: list[dict],
    *,
    same_sector_exception_threshold: dict = {
        "sector_score": 2,
        "leader_score": 2,
        "sector_avg_change_pct": 5.0,
    },
) -> list[dict]:
    ordered = sorted(rows, key=candidate_priority)
    if len(ordered) < 2:
        return ordered[:1]

    first = ordered[0]
    first_sector = _sector_key(first)

    # Default: 다른 섹터 2등
    for row in ordered[1:]:
        if _sector_key(row) != first_sector:
            # 같은 섹터 예외 우선 체크
            if _same_sector_strong_exception_applies(
                first, ordered, same_sector_exception_threshold
            ):
                # 같은 섹터의 대장 2등주도 허용
                same_sector_2nd = next(
                    (r for r in ordered[1:] if _sector_key(r) == first_sector
                     and int(r.get("score_leader", 0)) == 2),
                    None
                )
                if same_sector_2nd is not None:
                    return [first, same_sector_2nd]
            return [first, row]

    # 다른 섹터 후보 없음 + 같은 섹터 예외 성립 → 같은 섹터 대장 2종목
    if _same_sector_strong_exception_applies(first, ordered, ...):
        same_sector_2nd = next((r for r in ordered[1:] if ...), None)
        if same_sector_2nd:
            return [first, same_sector_2nd]

    return [first]  # 1종목만
```

### 5.3 10분 재평가 교체 규칙 (Phase D)

```python
REPLACEMENT_THRESHOLD = 1.10              # 10% 이상 강해야 교체
REPLACEMENT_COOLDOWN_MIN = 5              # 같은 종목 5분 내 재교체 금지
REPLACEMENT_FREEZE_AFTER = time(19, 45)   # 19:45 이후 교체 금지

def should_replace(current: CandidateTop2, new: CandidateTop2, history: list) -> bool:
    now = datetime.now(SEOUL_TZ).time()
    if now >= REPLACEMENT_FREEZE_AFTER:
        return False

    current_strength = current.score_total + current.context_bonus
    new_strength = new.score_total + new.context_bonus
    if new_strength < current_strength * REPLACEMENT_THRESHOLD:
        return False

    # 쿨다운 체크
    recent_events = [h for h in history
                     if h.stock_code == new.stock_code
                     and h.at > datetime.now(SEOUL_TZ) - timedelta(minutes=REPLACEMENT_COOLDOWN_MIN)]
    if recent_events:
        return False

    return True
```

### 5.4 매수 tranche 가격 전략 (Phase E)

```python
class BuyTrancheSpec:
    tranche: str
    time: time
    ratio: float
    price_strategy: Literal["MAKER_BID_PLUS_TICK", "LAST", "TAKER_ASK"]

TRANCHES = [
    BuyTrancheSpec("T1", time(19,50), 0.40, "MAKER_BID_PLUS_TICK"),
    BuyTrancheSpec("T2", time(19,54), 0.30, "LAST"),
    BuyTrancheSpec("T3", time(19,58), 0.30, "TAKER_ASK"),
]

def compute_buy_price(snapshot: QuoteSnapshot, strategy: str, tick_size: int) -> int:
    if strategy == "MAKER_BID_PLUS_TICK":
        return snapshot.bid1 + tick_size
    if strategy == "LAST":
        return snapshot.last
    if strategy == "TAKER_ASK":
        return snapshot.ask1
```

### 5.5 매도 스케줄 + 추격 (Phase F)

```python
SELL_SCHEDULE = [
    # (시각, 잔량대상, 가격전략)
    (time(8, 0,  0), "initial_50pct", "LAST"),
    (time(8, 2,  0), "remaining",     "LAST_MINUS_1PCT"),
    (time(8, 4,  0), "remaining",     "LAST_MINUS_2PCT"),
    (time(8, 5,  0), "remaining",     "BID1_TAKER"),
    # 08:06 ~ 08:49 : 1분 간격 BID1_TAKER 재발주 (interval job)
]
CHASE_INTERVAL_SEC = 60
HANDOVER_TO_KRX_AT = time(8, 50, 0)
MARKET_IOC_FINAL_AT = time(9, 0, 30)
EMERGENCY_STOP_LOSS_PCT = -3.0          # KRX 종가 대비 -3% 이상 시 즉시 테이커

def on_emergency_stop_detected(position: Position, current_price: int):
    """긴급 손절 스레드 (1분 간격 현재가 확인)"""
    drop_pct = (current_price - position.reference_close) / position.reference_close * 100
    if drop_pct <= EMERGENCY_STOP_LOSS_PCT:
        trade_executor.cancel_pending_sell_orders(position.stock_code)
        trade_executor.place_bid1_taker_all(position.stock_code, position.remaining_qty)
```

### 5.6 예수금 제약 + 몰빵 룰 (Phase E)

```python
def compute_allocation(deposit: int, candidates: list[Candidate]) -> dict[str, int]:
    """
    - 2종목: 종목당 deposit * 0.45 (10% 버퍼)
    - 1종목: deposit * 0.90
    - 1등 종목 1주 가격 > allocation → 1등 종목에 deposit * 0.90 몰빵
    """
    if len(candidates) == 2:
        per_stock = int(deposit * 0.45)
        result = {}
        for c in candidates:
            qty = per_stock // c.entry_price
            if qty == 0:
                # 몰빵 fallback
                return {candidates[0].stock_code: int(deposit * 0.90) // candidates[0].entry_price}
            result[c.stock_code] = qty
        return result
    if len(candidates) == 1:
        return {candidates[0].stock_code: int(deposit * 0.90) // candidates[0].entry_price}
    return {}
```

### 5.7 안전장치 (Phase G)

```python
# guards.py
KILL_SWITCH_PATH = Path(".bkit/state/auto_trade_enabled")
PAPER_MODE_PATH = Path(".bkit/state/paper_mode")
DAILY_LOSS_LIMIT_PCT = -5.0              # -5%
CONSECUTIVE_FAIL_LIMIT = 3

def check_allowed(action: str, ctx: dict) -> GuardDecision:
    """모든 job/order 전에 호출"""
    if _kill_switch_off():
        return GuardDecision(allowed=False, reason="KILL_SWITCH_OFF")
    if _daily_loss_exceeded():
        return GuardDecision(allowed=False, reason="DAILY_LOSS_LIMIT")
    if _consecutive_failures() >= CONSECUTIVE_FAIL_LIMIT:
        _flip_paper_mode()
        return GuardDecision(allowed=True, paper=True, reason="PAPER_MODE_AUTO")
    if _paper_mode_on():
        return GuardDecision(allowed=True, paper=True)
    return GuardDecision(allowed=True, paper=False)
```

### 5.8 Slack 알림 + 60초 취소 창 (Phase G)

```python
async def slack_notify_and_wait_cancel(order_spec: OrderSpec, wait_sec: int = 60) -> bool:
    """
    True 반환: 발주 진행
    False 반환: 사용자가 'cancel' 응답, 발주 중단
    """
    msg_id = await slack.post_message(
        channel=SLACK_CH_ORDERS,
        text=f":robot: 발주 예정 {order_spec.summary()}  | `cancel` 입력 시 60초 내 취소"
    )
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        replies = await slack.get_replies(msg_id)
        if any(r.lower().strip() == "cancel" for r in replies):
            return False
        await asyncio.sleep(2)
    return True
```

---

## 6. Session Guide (for `/pdca do --scope`)

### 6.1 Module Map

| Module Key | 설명 | 의존성 |
|-----------|------|--------|
| `module-a-nxt` | Phase A: NXT 리스트 + 플래그 + UI 배지 + 감사 리포트 | 없음 (독립 착수 가능) |
| `module-b-supply` | Phase B: 수급 연속성 + material_news + trader_style | 없음 (엔진 내부) |
| `module-c-extract` | Phase C: 15:30 배치 + Top 2 선정 로직 | a, b |
| `module-d-briefing` | Phase D: 19:30 브리핑 + SSE + 10분 재평가 | c, h(부분) |
| `module-e-buy` | Phase E: 자동매수 + kiwoom_order + trade_executor buy flow | a, c |
| `module-f-sell` | Phase F: 자동매도 스케줄 + 긴급손절 + KRX 이관 | e |
| `module-g-safety` | Phase G: guards + kill switch + daily P/L + paper mode + Slack | e, f |
| `module-h-perf` | Phase H: asyncio 재작성 + 캐시 + WebSocket 구독 + 라디오 UI 제거 | 독립 (C보다 먼저 완료 권장) |

### 6.2 Recommended Session Plan (8-10 sessions)

| 세션 | `--scope` | 주 산출물 | 예상 기간 |
|-----|----------|---------|----------|
| S1 | `module-a-nxt` | NXT CSV + 스키마 확장 + 배지 UI + 감사 리포트 v0 | 1.5일 |
| S2 | `module-h-perf` (우선) | 수집 배치 asyncio 재작성 + 캐시 → **15:30 run 90s 이내 확인** | 2일 |
| S3 | `module-b-supply` | supply 연속성 + material_news + trader_style | 1.5일 |
| S4 | `module-c-extract` | 15:30 배치 + Top 2 섹터 다양성 + candidate_set_v3 | 1일 |
| S5 | `module-d-briefing` (앞부분) | post_close_briefing 파이프라인 (4축) | 1.5일 |
| S6 | `module-d-briefing` (UI) | SSE 엔드포인트 + React 훅 + 실시간 배지 + 교체 로직 | 1.5일 |
| S7 | `module-e-buy` | kiwoom_order + trade_executor 매수 + 19:50/54/58 tranche | 2일 |
| S8 | `module-f-sell` | 매도 스케줄 + 추격 + 긴급손절 + KRX 이관 | 2일 |
| S9 | `module-g-safety` | guards.py + kill switch + P/L + paper + Slack | 1일 |
| S10 | 통합 시험 + QA | paper mode로 1주일 실전 시뮬 후 실계좌 전환 | 5일 |

총 예상: ~20일 (10일 구현 + 5일 paper 검증 + 5일 실전 안정화)

---

## 7. Test Plan (L1~L5)

### 7.1 L1 API

- `GET /api/closing-bet/candidates?date=2026-04-23` → 200, `{candidates: [{rank:1,...}, {rank:2,...}]}` 구조
- `GET /api/closing-bet/candidates` 인증 없이 200 (read-only) 또는 지정된 가드 정책 반영
- `POST /api/controls/killswitch` with `{enabled: false}` → 200 + 파일 `.bkit/state/auto_trade_enabled` 내용 `0`
- `GET /api/closing-bet/stream` SSE 연결 유지 + `event:` 라인 형식 검증

### 7.2 L2 UI Actions

- CandidateTop2View 렌더 → 카드 2개 표시 + NXT 배지 + 권장 시간대 표시
- SSE 이벤트 `candidate.replaced` 수신 시 카드 교체 애니메이션 5초간 `REPLACED` 배지
- KillSwitchPanel 토글 → POST 호출 + 배지 색상 변경

### 7.3 L3 E2E Scenarios

- **시나리오 1 (Happy Path)**: 15:30 배치 → 19:30 브리핑 → 19:50/54/58 매수 → 익일 08:00/02/04/05 매도 → 09:10 리포트 (paper mode)
- **시나리오 2 (교체)**: 15:30 Top 2 중 한 종목이 19:40 재평가 시 더 강한 종목으로 교체됨 → UI 반영 → 매수 대상 변경
- **시나리오 3 (Kill Switch)**: 19:49에 kill switch OFF → 19:50 발주 시점 guard가 차단 → `auto_orders` 테이블에 `FAILED` 기록 + Slack 알림
- **시나리오 4 (긴급 손절)**: 다음날 08:00 KRX 종가 대비 -4% 현재가 → 긴급 스레드가 즉시 매수1호가 전량 발주
- **시나리오 5 (예수금 몰빵)**: 후보 2개, 2등 종목 1주 가격이 할당보다 큼 → 1등에 몰빵
- **시나리오 6 (08:50 이관)**: 08:49까지 미체결 10주 → KRX 동시호가 이관 → 09:00 체결 확인

### 7.4 L4 Performance (Enterprise)

- 15:30 전체 배치 end-to-end < **90초** (asyncio 병렬화 후)
- 19:30 재평가 배치(2종목) < **15초**
- SSE 이벤트 지연(생성 → 브라우저 수신) < 1초

### 7.5 L5 Security

- 키움 appkey/secretkey 파일이 `.gitignore` 처리 + 프로세스 환경에서만 읽히는지
- `POST /api/controls/killswitch`가 인증 가드 뒤에 있는지 (로컬 only 또는 basic auth)
- 주문 감사 로그 `.bkit/audit/orders.jsonl`이 append-only 퍼미션인지
- Slack webhook URL 노출 방지

---

## 8. Risk & Mitigation (Design 관점)

| 리스크 | 설계 대응 |
|--------|----------|
| APScheduler 데몬 크래시 시 19:50 tranche 누락 | systemd `Restart=always` + 15초 `RestartSec`. + 매 tranche 직전 "다음 tranche 예약 확인" 로그. tranche 누락 감지 시 즉시 Slack 긴급 알림 |
| 중복 발주 (재시작 후 같은 cron 재실행) | `auto_orders.idempotency_key = {date}_{ticker}_{side}_{tranche}`. DB unique 제약 위반 시 skip + info log |
| 키움 WebSocket 연결 끊김 | WS polling으로 fallback (5초 간격) + Slack 경고 |
| NXT 지정가 호가 추격 무한루프 | 08:50 hard deadline + KRX 이관 + 09:00:30 시장가 IOC 최종 백업 |
| 배치 H를 C/D 앞에 못 넣어 성능 미달 | S2에 H 먼저 배치 (권장 Session Plan). 미달 시 S4 진입 차단 게이트 |
| SSE 브라우저 탭 닫힘 후 이벤트 손실 | 클라이언트 재연결 시 `Last-Event-ID` 헤더로 누락분 복원 |
| 예수금 조회 실패 | guards에서 API 체크 → 실패 시 paper mode 자동 전환 |
| US 선물 데이터 소스 부재 | 초기 구현은 Yahoo Finance 파서로 시작, 장애 시 이 축만 N/A 처리하고 나머지 3축으로 판단 |

---

## 9. Observability

- **Slack 채널**: `#stocks-orders`(발주/체결), `#stocks-alerts`(kill switch/paper mode/긴급 손절), `#stocks-daily`(09:10 리포트)
- **감사 로그**: `.bkit/audit/orders.jsonl` (append-only, 매 주문 이벤트 1줄 JSON)
- **스케줄러 로그**: `runtime/logs/scheduler.log` (info 이상, 10MB 로테이션)
- **DB 메트릭 뷰**: `v_daily_ops_summary` (매일 15:30 배치 소요 / 19:30 재평가 소요 / 매수 체결률 / 매도 체결률 / 일 P/L / kill switch 토글 카운트)

---

## 10. Dependencies (신규)

```toml
# pyproject.toml 추가
dependencies = [
    "apscheduler>=3.10",
    "httpx>=0.27",           # asyncio HTTP (기존 requests 대체 일부)
    "slack-sdk>=3.26",
    "sse-starlette>=2.1",    # FastAPI SSE
]
```

```json
// frontend/package.json 추가 (SSE는 네이티브 EventSource로 충분)
"@microsoft/fetch-event-source": "^2.0.1"  // optional, reconnect 용이
```

---

## 11. Implementation Guide (요약)

### 11.1 순서 요약

1. **S1**: `module-a-nxt` — 내일 오후 배지 확인 가능 상태 달성
2. **S2**: `module-h-perf` — 배치 속도 목표 충족 (필수 선행)
3. **S3**: `module-b-supply` — 점수 체계 확장
4. **S4~S6**: `module-c,d` — 15:30 배치 + 19:30 브리핑 + SSE UI
5. **S7~S8**: `module-e,f` — 자동매수/매도 (paper mode로 먼저 시험)
6. **S9**: `module-g-safety` — 안전장치 완성
7. **S10**: 통합 + paper mode 1주 시뮬 → 실계좌 전환

### 11.2 주요 Dev Commands

```bash
# 스케줄러 데몬 수동 실행 (개발)
python -m batch.runtime_source.scheduler

# paper mode 켜기
echo "1" > .bkit/state/paper_mode

# kill switch off
echo "0" > .bkit/state/auto_trade_enabled

# NXT 리스트 수동 갱신
python -m batch.scripts.refresh_nxt_tickers

# 15:30 배치 즉시 실행 (테스트)
python -m batch.runtime_source.pipelines.daily_candidate_extract --date 2026-04-23

# 19:30 브리핑 즉시 실행
python -m batch.runtime_source.pipelines.post_close_briefing --date 2026-04-23
```

### 11.3 Session Guide

§6 참조.

---

## 12. 미결정 사항 (Design 단계에서 열어두고 Do에서 확정)

- NXT 리스트 파싱 방식: nextrade.co.kr HTML 크롤러 vs 증권사 공지 CSV vs 키움 API 응답 필드 — **S1에서 결정**
- 키움 WebSocket 체결 이벤트 스펙 상세 — **S7 착수 시 확인**
- US 선물 데이터 소스 최종 선정 — **S5에서 결정** (Yahoo 우선 후보)
- Slack 봇 등록 + `cancel` 응답 파싱 — **S9에서 봇 토큰 발급 필요**
- `.bkit/state/paper_mode` 자동 해제 조건 (현재: 3일 성공이면 자동? 또는 수동만?) — **S9에서 결정**
- Ticker tick size 테이블 소스(호가 단위) — **S7에서 확정** (키움 API 혹은 KRX 공표 테이블)

---

## 13. 참조

- Plan: `docs/01-plan/features/nxt-closing-bet-v2.plan.md`
- 기존 전략 원칙: `docs/CLOSING_BET_PRINCIPLES.md`
- 엔진: `batch/runtime_source/engine/{generator,scorer,decision_policy,position_sizer}.py`
- 기존 키움 클라이언트: `batch/runtime_source/providers/kiwoom_client.py`

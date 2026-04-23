# 전략 감사 리포트 v0 (2026-04)

작성일: 2026-04-22
범위: 종가배팅 엔진 v2 (현재 코드 기준)
참조: `docs/CLOSING_BET_PRINCIPLES.md`, `docs/01-plan/features/nxt-closing-bet-v2.plan.md`
상태: **v0 초안** — 정량 실측은 배치 재작성(Phase H) 이후 1주 run 데이터로 채움

---

## 1. 요약

22점 만점 12축 점수 체계·시장 보정·등급 강등 등 **이론 필터**는 코드와 문서가 일치한다. 반면 **뉴스 차단 로직**과 **수급 연속성**에 허점이 있고, **NXT 인식은 부재**하며 **포트폴리오 집행**(일 손실 한도·시간손절·자동 주문)은 아예 구현되어 있지 않다. v3 Plan의 Phase A~H가 이를 단계적으로 해소한다.

## 2. 상태 범례

- ✅ OK — 문서와 코드 일치
- ⚠️ GAP — 부분 일치 또는 잠재적 우회 경로 존재
- ❌ MISSING — 전혀 구현되지 않음
- 📝 TBV — 정량 검증 필요 (배치 재작성 후 실측)

## 3. 항목별 감사 결과

### 3.1 이론 필터 (OK)

| 원칙 | 코드 위치 | 상태 |
|------|----------|:---:|
| 22점 만점 12축 | `batch/runtime_source/engine/scoring_constants.py:TOTAL_RULE_SCORE_MAX` | ✅ |
| 뉴스 0이면 NEWS_BLOCKED | `engine/decision_policy.py:184` | ✅ (단 3.2 G1 참조) |
| RISK_OFF=매수차단, CAUTION+B=차단 | `engine/decision_policy.py:190-199` | ✅ |
| 등급 강등: CAUTION 1단계, RISK_OFF 2단계 | `engine/decision_policy.py:_shift_grade` | ✅ |
| 위험점수 50 기준, 외부시장 `(risk-50)*0.7` 가산 | `engine/decision_policy.py:101-104` | ✅ |
| BUY 총점 하한 8 | `engine/decision_policy.py:176` (`BUY_SCORE_THRESHOLD`) | ✅ |
| ETF/ETN 제외 | `engine/config.py:exclude_etf/etn=True` | ✅ |
| 뉴스 유효 구간 전일 15:30~당일 23:59 | `engine/news_window.py` | ✅ |
| 08:00 NXT / 09:00 KRX 성과 비교 | `backend/app/services/performance_service.py:quick_refresh` | ✅ (분석용) |

### 3.2 허점 (GAP)

#### G1. ⚠️ 뉴스 fallback 1점 → NEWS_BLOCKED 우회 (HIGH)

**증거**: `engine/scorer.py:64-76`
```python
if not news_list:
    score.news = no_news_score   # = 0
elif llm_result and str(llm_meta.get("status")) == "OK":
    score.news = max(0, min(3, llm_score))
else:
    score.news = default_news_score   # = 1  ← fallback
```
그리고 `engine/decision_policy.py:184`:
```python
if fresh_news == 0:   # fresh_news_count == 0 일 때만 차단
    ...
```

→ 실제로는 `news_list`에 synthetic/낮은 품질 뉴스 1건이라도 있으면 `fresh_news_count >= 1`이 되어 NEWS_BLOCKED를 피하고, 총점에는 fallback 1점이 붙는다. "실체 없는 테마 뉴스"가 그대로 통과할 수 있다.

**대책 (Phase B)**: `material_news_count`(LLM OK + `material_strength ≥ 0.3`) 필드를 신설해 `decision_policy`의 차단 기준을 이걸로 대체.

#### G2. ⚠️ 손절 -3% / 익절 +5% 고정 (MED)

**증거**: `engine/position_sizer.py:calculate` → `config.stop_loss_pct`, `config.take_profit_pct` 하드코딩.

**대책 (Phase B)**: `trader_style: "default" | "scalper"` enum 도입. `scalper`는 `stop=-2%, target=+2%` (수급단타왕 원칙).

#### G3. ⚠️ 수급 연속성 미반영 (HIGH)

**증거**: `engine/scorer.py` 수급 점수는 `foreign_5d > 0` + `inst_5d > 0` **합산만** 확인. "5일 중 며칠 연속 순매수"는 추적 안 됨. 수급단타왕식 "매일매일 매집되는 종목" 개념 부재.

**대책 (Phase B)**: 배치에서 `continuity_days_foreign`, `continuity_days_institution` 집계 + 점수 가산.

#### G4. ❌ 포트폴리오 집행 규칙 미구현 (HIGH)

문서 §15가 "설정값 존재, 직접 집행 여부 미확인"으로 스스로 명시. 최대 보유 2, 일 손실 2R, 주 손실 4R, 갭상승 익절 +3%, 갭하락 손절 -2%, 시간손절 10시 — **전부 코드 실행 경로 없음**.

**대책 (Phase F/G)**: `trade_executor` + `guards.py`에서 집행.

#### G5. ⚠️ 스팩/우선주/리츠 제외 플래그 적용 경로 불명 (MED)

**증거**: `engine/config.py`에 `exclude_spac/preferred/reits = True` 및 `exclude_keywords` 리스트는 있으나, `generator.py`/`collectors.py`에서 이 플래그를 참조하는 로직이 `grep`로 명확히 잡히지 않음.

**대책 (Phase A 후속)**: 적용 경로 문서화 + 누락 시 `collectors.py`에 명시적 필터 추가. **TBV**.

#### G6. ❌ NXT 플래그 부재 (BLOCKER, 본 세션에서 해제)

**증거**: `stock_meta`/`tracked_picks`/`closing_bet_item` 어디에도 `nxt_eligible` 없음. `ClosingBetItem`에는 2026-04-22 기준 없음.

**상태**: **본 세션(Module A)에서 해제** — `data/nxt_tickers.csv` + `backend/app/services/nxt_lookup.py` + `ClosingBetItem.nxt_eligible` 추가 완료.

#### G7. ⚠️ 진입가가 단일 `current_price` — 실제 체결 시점과 불일치 (HIGH)

**증거**: `backend/app/services/closing_bet_service.py:_to_item`에서 `entry_price = row.entry_price`를 그대로 사용. 실제 15-16시 수동 매수 체결가와 산포 큼.

**대책 (Phase E)**: `trade_executor`가 실제 체결가를 `auto_orders.filled_avg_price`에 기록. 리포트는 이걸 기준으로 재계산.

#### G8. ❌ 다음날 갭하락 자동 손절 / 시간손절 없음 (HIGH)

**대책 (Phase F)**: 매도 스케줄 + 긴급 손절 스레드(-3% 이상 급변 감지 즉시 매수1호가 테이커).

#### G9. ⚠️ featured 5 선정이 이중 구현 (LOW)

**증거**: `closing_bet_service.get_closing_bet:210-220` 자체 로직 vs `pick_selector.select_top_candidates`. 서로 동기화 안 되면 결과 달라질 수 있음.

**대책 (Phase A 후속)**: `pick_selector`로 단일화.

#### G10. 📝 수집 배치 속도 느림 (BLOCKER)

**증거**: `KiwoomRESTClient`가 모든 API 호출을 직렬(`self._min_interval_sec = 0.22`)로 처리. 병렬 없음. asyncio 미사용. 네이버 파이프라인 별도 실행.

**대책 (Phase H)**: asyncio 병렬화 + 딕셔너리 TTL 캐시 + WebSocket 구독. **목표: 15:30 run 90초 / 19:30 재평가 15초**.

**현재 실측**: TBV (Phase H 전후 비교).

#### G11. ❌ 자동 주문 실행 모듈 부재 (BLOCKER)

**증거**: 키움 REST/WS 클라이언트는 있으나 `place_limit_order`, `cancel_order`, `get_order_status` 함수 없음.

**대책 (Phase E)**: `batch/runtime_source/providers/kiwoom_order.py` 신설.

#### G12. ⚠️ NXT 애프터마켓(15:30~20:00) 실시간 데이터 수집 부재 (HIGH)

**증거**: `kiwoom_client.effective_venue`는 15:40 이후만 NXT로 인식. 20:00 이후 다시 KRX로 리셋되지만, 19:30 브리핑·19:50 매수 구간에 NXT 호가·체결을 실제로 수집하는 배치가 없음.

**대책 (Phase D)**: `post_close_briefing.py`에서 NXT 호가 스냅샷 수집 + `effective_venue`를 08:00~20:00 풀레인지로 확장.

#### G13. ⚠️ 네이버/키움 라디오 선택 UI가 자동 루프에서 무의미 (LOW)

**대책 (Phase H)**: 라디오 제거 + 배치 카드에 "데이터 소스" 메타 문자열 표시.

### 3.3 실측 필요 (TBV)

배치 재작성(Phase H) 완료 후 1주 run 데이터로 채워 v1로 재발간.

| 지표 | 측정 방법 | 목표 |
|------|---------|------|
| featured 5종목 중 NXT 가능 비율 | `data/nxt_tickers.csv` JOIN | 60% 이상 (추정) |
| `fresh_news_count >= 1` ∧ LLM `NO_RESULT` 비율 | `signals` 테이블 COUNT | 20% 미만이면 G1 영향 제한적 |
| `exclude_spac/preferred/reits` 미적용 featured 유입 사례 | 종목명 수동 육안 + SQL | 0건 기대 |
| 15:30 배치 전체 run 시간 | 배치 로그 | 90초 |
| 19:30 재평가 시간 (2종목 기준) | 배치 로그 | 15초 |
| 수동 매수 시점 편차 | PerformanceView 기록과 엔진 `entry_price` diff | 평균 ±0.3% 기대 (현재는 산포 큼) |

## 4. 허점 우선순위 매트릭스

| Gap | 심각도 | Phase | 상태 |
|-----|:------:|:-----:|:----:|
| G1 뉴스 fallback | HIGH | B | pending |
| G3 수급 연속성 | HIGH | B | pending |
| G6 NXT 플래그 | BLOCKER | A | **resolved** |
| G7 진입가 단일값 | HIGH | E | pending |
| G8 갭하락 손절 | HIGH | F | pending |
| G10 배치 속도 | BLOCKER | H | pending |
| G11 자동주문 모듈 | BLOCKER | E | pending |
| G12 NXT 실시간 수집 | HIGH | D | pending |
| G2 손절 고정 | MED | B | pending |
| G4 포트폴리오 규칙 | MED | F/G | pending |
| G5 제외 플래그 경로 | MED | A 후속 | pending |
| G9 featured 이중 구현 | LOW | A 후속 | pending |
| G13 라디오 UI | LOW | H | pending |

## 5. 본 세션(Module A)에서 달성한 것

- ✅ G6 해제: NXT 플래그 체계 구축
  - 신규: `data/nxt_tickers.csv` (샘플 10종목, 추후 800종목 전환)
  - 신규: `batch/scripts/refresh_nxt_tickers.py` (CSV 유효성 검사 + `--fetch` 자동 파싱 훅)
  - 신규: `backend/app/services/nxt_lookup.py` (싱글톤 + 파일 mtime 기반 자동 리로드 + `stale` 판정)
  - 수정: `backend/app/schemas/closing_bet.py` (`nxt_eligible`, `recommended_window`, `recommended_order_type`)
  - 수정: `backend/app/services/closing_bet_service.py` (`_nxt_plan` 추가)
  - 수정: `frontend/src/types/api.ts` (3필드 추가)
  - 수정: `frontend/src/components/closing/ClosingTable.tsx` (거래소 배지 컬럼)
- ✅ v0 감사 리포트(본 문서) 발간

## 6. 다음 세션 권장 (Design §6.2 Session Plan 기반)

**S2 (`module-h-perf`)** — 배치 재작성 먼저. 성능 미달이면 S3~S6 진입 차단 게이트.

```
/pdca do nxt-closing-bet-v2 --scope module-h-perf
```

## 6B. 2차 세션(Module H Part 1) 결과

신규:
- `batch/runtime_source/providers/cache.py` — TTL 딕셔너리 캐시 (QUOTE/META/NEWS/UNIVERSE 4개 싱글톤, 스레드 안전)
- `batch/runtime_source/providers/kiwoom_client_async.py` — httpx 기반 asyncio 키움 클라이언트 (세마포어=8, 429 backoff, 통계 수집)
- `batch/scripts/bench_async_client.py` — async vs sync 벤치마크 스크립트

수정:
- `frontend/src/components/batch/BatchStatusView.tsx` — 네이버/키움 라디오 제거, "Active Source" 읽기 전용 배지로 대체
- `frontend/src/app/App.tsx` — `batchSource` 기본값 `'naver'` → `'kiwoom'`

### Module H Part 2 (다음 세션 필요)

본 세션은 **인프라 추가** 중심. 아래는 기존 직렬 파이프라인을 async로 리팩터하는 큰 작업이라 별도 세션:

1. `batch/runtime_source/pipelines/kiwoom_bootstrap_collect.py` — `KiwoomRESTClient` 호출을 `AsyncKiwoomClient.gather`로 대체
2. `batch/runtime_source/engine/collectors.py` — 종목 루프 내 동기 호출을 async로 전환
3. `batch/runtime_source/engine/generator.py` — 이미 async 골조가 있으나 collectors까지 일관되게 연결
4. `batch/runtime_source/pipelines/naver_bootstrap_collect.py` — 뉴스 fallback 전용으로 격하 (키움 뉴스 응답 비었을 때만 호출)
5. 실측: `python -m batch.scripts.bench_async_client --n 50` 로 sync vs async 차이 확인 → 90초/15초 목표 달성 여부 판단

### 실측 제안

```bash
# 사전: 키움 토큰 캐시 워밍업
python -X utf8 -c "from batch.runtime_source.providers.kiwoom_client import KiwoomRESTClient; KiwoomRESTClient().access_token()"

# 벤치
python -X utf8 -m batch.scripts.bench_async_client --n 20 --mode both --concurrency 8
python -X utf8 -m batch.scripts.bench_async_client --n 50 --mode async --concurrency 12
```

기대: 20종목 기준 sync ~5-8초 → async ~1-2초 (대략 4-5x 개선). 실제 값으로 §3.3 TBV 테이블 채우기.

## 7. 참조

- `docs/01-plan/features/nxt-closing-bet-v2.plan.md` §2.2 (허점 표)
- `docs/02-design/features/nxt-closing-bet-v2.design.md` §2.2 (Phase별 파일 매트릭스)
- `docs/CLOSING_BET_PRINCIPLES.md` §15 (미구현 명시 목록)

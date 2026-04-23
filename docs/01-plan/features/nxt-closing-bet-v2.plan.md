# Plan: NXT 종가배팅 v3 - 자동매매 + NXT 단일 트랙 + 자동 반복 루프

작성일: 2026-04-22 (v3 개정)
작성자: 운영자
기반: `docs/CLOSING_BET_PRINCIPLES.md`, 현재 `stocks_new` 엔진 v2

> v2(수동 투트랙)에서 v3(자동매매 + NXT 단일)로 전면 개정. 수동 매수는 폐기되고, 전 과정이 스케줄 배치로 자동화된다.

---

## Context Anchor (bkit v2.0.5)

- **WHY**: NXT 애프터마켓(15:30~20:00)은 장후 4시간 뉴스/수급/미국 프리마켓이 반영된 "진짜 종가"를 만든다. 기존 수동 매수(15-16시 아무때나)는 타이밍 산포가 커서 전략 재현성이 없었고, 지금까지 3-4시 사이 수동 클릭으로 매수하던 방식을 **자동화 + NXT 단일 트랙**으로 전환한다. NXT 불가 종목은 아예 제외 — 단일 거래소·단일 시간대로 재현성을 확보한다.
- **WHO**: 운영자 본인(확인/kill switch만). 모든 체결은 자동.
- **RISK**: (1) 자동 주문 오체결/중복체결, (2) NXT는 **시장가 불가, 지정가 only**(08:00~08:50, 15:30~20:00) — 유동성 얇으면 미체결, (3) 다음날 08:05 목표 청산 실패 시 NXT 08:50 종료까지 호가 추격 필요, (4) 예수금 200만원 제약으로 고가 종목 비중 왜곡, (5) 수집 배치 속도가 느려 10분 간격 재평가 시간에 못 맞춤.
- **SUCCESS**: (a) 15:30 자동 배치 → 2종목 후보 확정, (b) 19:30부터 10분 간격 재평가 + 더 강한 종목 발견 시 교체 + UI 실시간 업데이트, (c) **19:50 40% / 19:54 30% / 19:58 30% 자동매수**(지정가, 시간 경과에 따라 메이커→테이커로 이동), (d) **익일 08:00 자동매도**(08:00 현재가 → 08:02 -1% → 08:04 -2% → 08:05 매수1호가 → 이후 호가 추격 → NXT 메인 09:00:30 시장가 잔량 청산), (e) kill switch + 일일 손실 -5% 자동 차단 + 3일 실패 시 paper mode 자동 전환, (f) 수집 배치 전면 재작성(키움 단일화 + 병렬 + 캐시).
- **SCOPE**: 엔진(scorer/decision_policy/position_sizer), 배치(수집 성능 재작성 + 15:30/19:30-19:50/08:00-09:00 자동 스케줄), 주문 실행 모듈 신설(`trade_executor`), 백엔드(실시간 후보 API + WebSocket/SSE 푸시), 프론트(실시간 카드 업데이트 + kill switch UI), 문서(감사 리포트 + 운영 SOP).

---

## 1. 문제 정의 (Problem Statement)

기존 v2 Plan에서 운영자는 15-16시 사이 수동으로 featured 5종목을 매수하고 있었다. v3에서 운영자는 이 기능을 **완전 자동화**하기로 결정했다.

새 요구사항의 본질은 세 가지다.

1. **수동 매수 폐기**: 3-4시 사이 아무때나 수동 클릭 → 15:30 자동 배치 + 19:50~19:59 자동 주문으로 대체.
2. **NXT 단일 트랙**: NXT 불가 종목은 아예 후보에서 제외. 15:22 KRX 매수 트랙 삭제. 단일 경로로 재현성과 분석 단순화.
3. **자동 반복 루프**: 매일 15:30(추출) → 19:30~19:50(재평가 + 브리핑) → 19:50~19:59(매수) → 익일 08:00~08:50(매도)까지 사람 개입 없이 돌아간다. 운영자는 kill switch와 결과 리포트만 본다.

동시에 드러나는 기존 시스템 부채도 이번에 처리한다.

- 수집 배치가 매우 느려서 10분 간격 재평가 요구를 못 맞춘다.
- 네이버/키움 데이터 소스 라디오 선택 UI는 자동 루프에서는 무의미하다.
- 키움 주문 API는 이미 연결되어 있으나 실제 주문 실행 모듈이 없다.

---

## 2. 전략 감사 결과 (문서 vs 코드 Gap)

### 2.1 일치(OK) 항목

| 원칙 | 코드 위치 | 상태 |
|------|----------|------|
| 22점 만점 12축 점수 체계 | `engine/scorer.py` + `scoring_constants.TOTAL_RULE_SCORE_MAX` | OK |
| 뉴스 0이면 `NEWS_BLOCKED` | `decision_policy.decide_trade_opinion` L184 | OK |
| 시장 RISK_OFF=매수차단, CAUTION+B=차단 | `decision_policy` L190-199 | OK |
| 등급 강등: CAUTION 1, RISK_OFF 2 | `decision_policy._shift_grade` | OK |
| 총점 매수 하한 `BUY_SCORE_THRESHOLD=8` | `decision_policy` L176 | OK |
| ETF/ETN 제외 | `engine/config.py` | OK |
| 08시 NXT / 09시 KRX 성과 비교 | `performance_service.quick_refresh` | OK (분석용) |
| 뉴스 유효구간 전일 15:30~당일 23:59 | `engine/news_window.py` | OK |

### 2.2 허점 / 리스크

| # | 허점 | 현재 상태 | 영향 | 조치 |
|---|------|----------|------|------|
| G1 | 뉴스 있으면 fallback 1점 → 실체없는 테마가 NEWS_BLOCKED 우회 | `scorer.py` L64-76 | **HIGH** | Phase B: `material_news_count`(LLM OK + material_strength≥기준) 대체 |
| G2 | 손절 -3%/익절 +5% 고정 | `position_sizer.calculate` | MED | Phase B: `trader_style` enum, scalper=-2%/+2% |
| G3 | 수급 연속성 미반영 (5일 합산만) | `scorer.py` | **HIGH** | Phase B: `continuity_days_foreign/institution` 점수 가산 |
| G4 | 포트폴리오 집행 규칙(일손실/시간손절) 미구현 | — | **HIGH** | Phase G: trade_executor에서 집행 |
| G5 | 스팩/우선주/리츠 제외 플래그 적용 경로 불분명 | `config.exclude_*` | MED | Phase A: 필터 경로 문서화 + 실제 필터 삽입 |
| G6 | NXT 플래그 부재 | 전 테이블 | **BLOCKER** | Phase A 첫 작업 |
| G7 | 진입가 단일값, 실제 체결 시점과 불일치 | `closing_bet_service._to_item` | **HIGH** | Phase E: trade_executor가 실제 체결가 기록 |
| G8 | 다음날 갭하락 자동 손절 없음 | — | **HIGH** | Phase F: 매도 스케줄러 |
| G9 | featured 5 선정이 이중 구현 | `closing_bet_service` vs `pick_selector` | LOW | Phase A 단일화 |
| G10 | **수집 배치 속도 매우 느림** | `batch/runtime_source/pipelines/*` | **BLOCKER** | Phase H 전면 재작성 |
| G11 | **자동 주문 실행 모듈 없음** | — | **BLOCKER** | Phase E/F 신설 |
| G12 | **NXT 애프터마켓 실시간 데이터 수집 없음** | `kiwoom_client.effective_venue`가 15:40 기준이지만 이후 수집은 얕음 | **HIGH** | Phase C + D |
| G13 | 네이버/키움 라디오 선택 UI가 자동 루프에서 의미 없음 | `frontend` settings | LOW | Phase H에서 라디오 제거, 배치 카드에 "데이터 소스" 메타 표시 |

### 2.3 실측 검증 (Phase A 초반)

- 최근 30 run featured 5종목 중 NXT 가능 종목 비율 (리스트 확보 후 SQL)
- `fresh_news_count >= 1`인데 LLM이 `NO_RESULT`였던 종목 비율 → G1 영향
- 배치 수집 1회 전체 소요 시간 실측 (각 단계별 타임라인 로그)

---

## 3. NXT 대체거래소 이해 (정확 규칙)

### 3.1 시간대 및 **호가유형 제약**

| 세션 | 시간 | **가능한 호가유형** |
|------|------|-------------------|
| 프리마켓 | 08:00 ~ 08:50 | **지정가 only** |
| 메인마켓 | 09:00:30 ~ 15:20 | 지정가 / 중간가 / 시장가(IOC·FOK) |
| KRX 종가매매(NXT 위탁) | 15:30 ~ 16:00 | 지정가 (KRX 종가로 체결) |
| 애프터마켓 | 15:30 ~ 20:00 | **지정가 only** |

**중요**: 본 Plan의 주력 구간(19:50~19:59 매수, 08:00~08:50 매도)은 **둘 다 지정가 only**. 시장가 주문 자체가 불가능하다. 유동성 얇은 종목은 지정가를 호가에 맞춰 계속 갱신해야 체결된다.

### 3.2 핵심 규칙

- NXT 거래 가능 종목 약 800종목(KOSPI 380 + KOSDAQ 420), 시총/거래대금 상위.
- NXT 가능 종목은 KRX 시간외 단일가(16:00~18:00) 거래 불가.
- 수수료 KRX 대비 20~40% 저렴(메이커 0.0013%, 테이커 0.0018%).
- 거래소별 호가 독립.
- **다음날 KRX 09:00 기준가 = KRX 종가(15:30 확정)**. NXT 20시 종가가 아님 → 그래서 다음날 08:00 NXT 프리에서 파는 가격은 **KRX 종가 기준 갭률**이 포인트.

---

## 4. 수급단타왕(고명환) 반영 포인트

조사 결과는 v2와 동일. 본 Plan에서 반영 확정:

1. **수급 연속성 점수** (외인/기관 N일 연속 순매수) — Phase B
2. **-3% → -2% 손절 옵션화** (`trader_style`) — Phase B
3. **분할매수 vs 시장가 자동 추천** → NXT는 시장가 불가이므로 **"지정가 공격성 단계화"**로 치환. 19:50 메이커 → 19:54 중립 → 19:58 테이커 — Phase E
4. **실체없는 테마 뉴스 감점 강화** (`material_strength` 기반) — Phase B

---

## 5. 자동 반복 루프 전체 타임라인 (하루)

```
15:30  [배치] 추출 배치 실행
       - NXT 가능 종목만 대상
       - 매수 판정(adjusted_grade != C, total>=8, 뉴스 유효)
       - 섹터 다른 Top 2 선정 (§6 상세)
       - DB에 candidate_set_v3 저장
       - UI "오늘의 후보" 섹션 실시간 업데이트

19:30~19:40~19:50  [배치] 10분 간격 재평가 (3회)
       - 19:30, 19:40 각 시점에 실행
       - (a) 장후 브리핑 4축 점검 (§6.4)
       - (b) NXT 애프터마켓 현재 스냅샷으로 점수 재계산
       - (c) 기존 2종목 점수 vs 새 후보 점수 비교
       - (d) 새 후보가 "충분히 강하면" 교체 (§6.3 교체 임계값)
       - UI 실시간 푸시 (WebSocket or SSE)

19:50  [주문] 자동매수 1차 발주 (40%)
19:54  [주문] 자동매수 2차 발주 (30%)
19:58  [주문] 자동매수 3차 발주 (30%)
       - 각 tranche별 지정가 전략 §7.2

(익일)
08:00  [주문] 자동매도 1차 (50% 현재가 지정가)
08:02  [주문] 잔량 -1% 하향 지정가
08:04  [주문] 잔량 -2% 하향 지정가
08:05  [주문] 잔량 매수1호가(테이커) 재설정
08:06~ [주문] 1분마다 매수1호가 재조회하여 지정가 재설정 추격
08:50  [주문] NXT 프리 종료. 미체결이면 KRX 09:00 동시호가 이관
09:00:30 [주문] NXT 메인 재개 시 시장가(IOC)로 잔량 전량 청산 (백업 경로)

09:10  [배치] 전일 결과 집계 + kill switch 상태 점검 + 리포트
```

---

## 6. 종목 선정 로직 변경 (Top 5 → Top 2, NXT only)

### 6.1 풀 (Pool)

- 기존: 시장 상승률 상위 + ETF/ETN 제외
- **v3 신규**: 위 + `nxt_eligible == True` 필터

### 6.2 매수 후보 Top 2 선정 규칙

1. `decision_status == BUY` AND `nxt_eligible == True` 종목 전수 대상
2. `pick_selector.candidate_priority` 기존 우선순위로 정렬
3. **섹터 중복 제거**: 상위부터 섹터 다른 종목 2개 선정
4. **예외 - 같은 섹터 허용 조건**:
   - 해당 섹터의 `sector_score == 2` (섹터 1-2위)
   - AND 두 종목 각각 `score_leader == 2` (섹터 대장주)
   - AND 섹터 전체 상승률 평균 ≥ 5%
   - 이 모두 만족 시 **같은 섹터 2종목 허용**
5. Top 2가 확정되지 않는 경우(후보 부족):
   - 후보 1개만 있으면 해당 1개만 (자동 매수 수량은 예수금의 80% 이내)
   - 후보 0개면 **당일 자동매수 스킵**

### 6.3 19:30~19:50 재평가 교체 규칙

10분 간격(19:30, 19:40) 재평가 시:

- **교체 임계값**: 새 후보의 `(score_total + context_bonus)` ≥ 기존 후보 × **1.10** (10% 이상 강해야 교체)
- **교체 쿨다운**: 같은 종목을 5분 내 재교체 금지
- **19:45 이후 교체 금지**: 19:50 매수 직전에 갑자기 바꾸지 않음 (주문 준비 시간 확보)
- 교체 시 UI에 `REPLACED: 종목A → 종목B` 이벤트 배지 5초 표시

### 6.4 장후 브리핑 4축 (19:30, 19:40 각 시점 재실행)

v2 Plan과 동일. 4축:

1. **신규 뉴스 LLM 재평가** — `material_strength_deterioration` 플래그
2. **NXT 애프터 유동성** — 매수1호가 ±0.5% 잔량×수량 기준
3. **KRX 종가 vs 현재가 괴리 ±1.5%** 가드
4. **미국 ES/NQ 프리마켓 -1% 이상** 가드

하나라도 발동 → 해당 종목 **후보 강등** 또는 수량 50% 감축 자동 반영.

---

## 7. 자동매수 상세 (Phase E)

### 7.1 예수금 200만원 제약 아래 수량 계산

1. 예수금 조회 (키움 API)
2. 후보 2종목이면 종목당 할당 = `deposit * 0.45` (나머지 10% 수수료·슬리피지 버퍼)
3. 후보 1종목이면 할당 = `deposit * 0.90`
4. 수량 = `int(할당 / 현재가)`
5. 수량이 0이면 **"강한 1등 종목으로 몰빵"** (사용자 지시: "제일 쌘걸로 알아서 매수")
6. tranche별 수량 분할: 40% / 30% / 30%. 소수점 내림, 나머지 마지막 tranche

### 7.2 지정가 가격 전략 (시장가 불가 환경에서 체결 보장 vs 유리가 밸런스)

| Tranche | 시점 | 수량 | 지정가 | 의도 |
|---------|------|------|--------|------|
| 1 | 19:50 | 40% | **매수1호가 + 1틱** | 메이커 우선. 호가 내려오면 유리가 체결 |
| 2 | 19:54 | 30% | **현재가** | 중립. 직전 체결가 기준 |
| 3 | 19:58 | 30% | **매도1호가** | 테이커. 19:59에는 무조건 체결 보장 |

미체결 tranche는 다음 tranche 시점에 **이전 가격 취소 후 새 지정가 재발주**.

### 7.3 주문 실행 모듈 `batch/runtime_source/providers/kiwoom_order.py` (신설)

- `place_limit_order(ticker, side, qty, price, venue)` — 지정가 주문 발주
- `cancel_order(order_id)` — 주문 취소
- `get_order_status(order_id)` — 체결/미체결 조회
- `get_quote_snapshot(ticker)` — 매수1/매도1/현재가 조회
- 전 함수 호출 직전/직후 **Slack 알림** + 감사 로그 `.bkit/audit/orders.jsonl`

---

## 8. 자동매도 상세 (Phase F)

### 8.1 목표

- **가능한 한 빠르게 전량 청산**. 08:05가 목표이지 데드라인이 아님. 미체결이면 08:06, 08:07 ... 계속 호가 추격.
- 08:50(NXT 프리 종료) 이후에도 미체결이면 KRX 09:00 동시호가 이관 → 09:00:30 NXT 메인 재개 시 시장가(IOC)로 잔량 즉시 청산.

### 8.2 매도 스케줄

| 시점 | 대상 | 지정가 | 비고 |
|------|------|--------|------|
| 08:00:00 | 50% | **현재가** | 개장 즉시 절반 청산 |
| 08:02:00 | 잔량 | **현재가 × 0.99 (= -1%)** | 사용자 지정 스텝 |
| 08:04:00 | 잔량 | **현재가 × 0.98 (= -2%)** | 한 번 더 하향 |
| 08:05:00 | 잔량 | **매수1호가** (테이커) | 즉시 체결 지향 |
| 08:06~08:49 | 잔량 | 매수1호가, 1분마다 재조회·재발주 | NXT 프리 호가 계속 추격 |
| 08:50 | 잔량 | 지정가 취소 → KRX 동시호가 이관 | 09:00 시가 참여 |
| 09:00:30 | 잔량 | 시장가 IOC (NXT 메인) | 최종 백업. 잔량 0 보장 |

### 8.3 긴급 손절 스레드 (별도 루프)

- 08:00:00~09:00:30 전 구간에서 1분마다 현재가 확인
- **KRX 종가 대비 -3% 이상 급하락** 감지 → 위 스케줄 **즉시 중단**하고 매수1호가 전량 재발주(테이커)
- 사고/앱 파이도/테러 등 급변 시나리오 대비

### 8.4 매도 주문 조회 루프

- 각 주문 발주 후 WebSocket 체결 이벤트 구독 또는 5초 간격 polling
- 체결되면 잔량 갱신, 다음 스케줄 tranche 수량 자동 조정
- 일부 체결(부분 체결) 시 잔량만 다음 스케줄에 승계

---

## 9. 안전장치 4축 (Phase G)

사용자 지시에 따라 4개 모두 구현:

### 9.1 Slack/이메일 알림

- 매수/매도 주문 발주 직전 알림 → 60초 내 사용자가 `cancel` 키워드로 응답하면 주문 중단
- 매수/매도 체결 완료 알림
- 긴급 손절 발동 알림
- kill switch 상태 변경 알림

### 9.2 Kill Switch 파일

- 경로: `.bkit/state/auto_trade_enabled`
- `1` → 자동매매 활성
- `0` → 모든 주문 발주 직전 체크, 0이면 발주 중단 + Slack 경고
- 운영자가 SSH/파일 편집으로 언제든 토글

### 9.3 일일 최대 손실 한도

- 매일 09:10 전일 결과 집계 시 당일 실현 P/L 계산
- 누적 -5%(≈ -10만원) 도달 시 → 다음 시장일 자동 배치 **스킵** (kill switch 자동 0)
- 운영자 수동 복구 필요

### 9.4 Paper Mode 자동 전환

- 최근 3 거래일 연속 "주문 실패" 또는 "체결 0" 시 자동으로 paper mode 전환
- Paper mode: 모든 주문을 DB `paper_trades` 테이블에만 기록, 실주문 X
- 운영자가 문제 파악 후 수동 복구

---

## 10. 배치 성능 재작성 (Phase H)

### 10.1 현 상태 문제

- 배치 실행 매우 느림 (구체 수치는 Phase A 실측)
- 네이버/키움 데이터 소스 라디오 UI가 자동 루프에 무의미
- 10분 간격 재평가(19:30~19:50)를 현 속도로는 못 맞춤

### 10.2 재작성 방향

1. **키움 단일화**: 네이버 뉴스/시세 수집 파이프라인 제거 또는 키움이 주, 네이버는 뉴스 fallback만.
2. **asyncio 병렬**: `KiwoomRESTClient`의 직렬 호출(0.22s 간격)을 병렬 타겟당 세마포어 제어로 풀기. 단 전체 Rate Limit은 유지.
3. **캐시**: 1회 run 내 동일 종목 2회 조회 방지. 장 마감 후 변하지 않는 데이터(종목 메타, 뉴스) TTL 캐시.
4. **WebSocket 활용**: 실시간 호가/체결은 REST polling 대신 WS 구독 (`wss://api.kiwoom.com:10000/api/dostk/websocket`).
5. **라디오 UI 제거**: 네이버/키움 선택 라디오 삭제. 각 배치 카드에 "데이터 소스: 키움 (뉴스는 키움 우선, 부족 시 네이버 fallback)" 메타 문자열 표시.

### 10.3 성능 목표

- 15:30 배치 전체 run: **90초 이내**
- 19:30 재평가 배치 (2종목만): **15초 이내**

---

## 11. Phase 분할 (구현 순서)

### Phase A. NXT 인프라 + 전략 감사 (최우선, 1-2일)

- [ ] `data/nxt_tickers.csv` 수집 + `batch/scripts/refresh_nxt_tickers.py`(주 1회 월 새벽)
- [ ] `stock_meta.nxt_eligible` 컬럼 + lookup 서비스
- [ ] `ClosingBetItem` 스키마에 `nxt_eligible`, `recommended_window` 필드 추가
- [ ] 감사 리포트 `docs/strategy-audit-2026-04.md` (G1~G13 실측)

### Phase B. 수급단타왕 반영 (3-4일)

- [ ] `supply.continuity_days_foreign/institution` 집계
- [ ] `scorer.py` supply 가중치 재설계
- [ ] `material_news_count` 필드 + `decision_policy` 대체
- [ ] `trader_style` enum + `position_sizer` 옵션

### Phase C. 15:30 자동 배치 + Top 2 선정 (2일)

- [ ] cron 15:30 `batch/runtime_source/pipelines/daily_candidate_extract.py`
- [ ] `pick_selector.select_top_2_sector_diverse(rows, allow_same_strong_sector)` 신설
- [ ] `candidate_set_v3` 테이블 (date, rank, stock_code, score_snapshot, venue_plan)
- [ ] 프론트 "오늘의 후보 Top 2" 섹션

### Phase D. 19:30 장후 브리핑 + 10분 재평가 (3일)

- [ ] cron 19:30, 19:40 `post_close_briefing.py`
- [ ] 4축 구현(신규 뉴스/유동성/가격 괴리/미국 선물)
- [ ] 교체 로직 + 쿨다운
- [ ] 프론트 실시간 업데이트(WebSocket or SSE)

### Phase E. 자동매수 19:50~19:58 (3일)

- [ ] `kiwoom_order.py` 신설
- [ ] cron 19:50/19:54/19:58 tranche executor
- [ ] 지정가 가격 전략 (메이커→중립→테이커)
- [ ] 예수금 조회 + 수량 계산 + "몰빵" fallback
- [ ] 감사 로그 + Slack 알림

### Phase F. 자동매도 08:00~08:50 + 백업 (3일)

- [ ] cron 08:00 매도 스케줄러
- [ ] 08:02 -1%, 08:04 -2%, 08:05 테이커, 08:06~ 호가 추격
- [ ] 08:50 KRX 이관, 09:00:30 NXT 메인 시장가 IOC 백업
- [ ] 긴급 손절 스레드 (-3% 급변 감지)

### Phase G. 안전장치 4축 (2일)

- [ ] Slack/이메일 알림 (매수/매도/kill switch/긴급손절)
- [ ] `.bkit/state/auto_trade_enabled` kill switch
- [ ] 일일 -5% 자동 차단
- [ ] 3일 연속 실패 paper mode 자동 전환

### Phase H. 배치 성능 재작성 + UI 라디오 제거 (3-4일)

- [ ] `KiwoomRESTClient` asyncio 병렬화
- [ ] 캐시 레이어
- [ ] WebSocket 구독 실시간 호가/체결
- [ ] 네이버 수집 파이프라인 fallback 전용으로 격하
- [ ] 프론트 라디오 선택 UI 제거
- [ ] 배치 카드 "데이터 소스" 메타 표시

### Phase I. (차기 Plan 후보)

- 주간/월간 성과 자동 리포트
- 복수 계좌 운영
- 전략 AB 테스트 (trader_style default vs scalper 병행)
- 통계적 백테스트 프레임워크

---

## 12. 성공 기준 (Success Criteria)

- [ ] 15:30에 자동으로 NXT 가능 종목만 대상으로 Top 2 후보가 생성되어 UI에 표시됨
- [ ] 19:30, 19:40에 자동 재평가가 돌고 새 후보가 기존보다 10% 이상 강하면 교체됨 + UI 실시간 반영
- [ ] 19:50/19:54/19:58에 자동 지정가 주문이 각 40%/30%/30% 수량으로 발주됨
- [ ] 익일 08:00 자동 매도가 시작되고 08:50까지 잔량 0 달성 (평균 88% 이상 08:05 이내 청산)
- [ ] Kill switch 파일 토글로 언제든 자동매매 중단 가능
- [ ] 배치 수집 전체 run이 90초 이내에 끝남
- [ ] 네이버/키움 라디오 UI가 제거되고 배치 카드에 데이터 소스 메타가 표시됨
- [ ] 전략 감사 리포트의 G1-G13이 모두 구체 대책 또는 완료 상태

---

## 13. 리스크 & 완화

| 리스크 | 완화책 |
|--------|--------|
| **자동 주문 오체결/중복체결** | 주문 발주 전 60초 대기 + Slack 알림, kill switch 파일 체크, 주문 후 상태 확인 루프 |
| **NXT 유동성 얇아 08:05 이내 미체결** | 매도 08:06~08:49 1분 간격 호가 추격, 08:50 KRX 이관, 09:00:30 NXT 메인 시장가 IOC 최종 청산 |
| **예수금 200만원 제약 고가 종목 왜곡** | 수량 0이면 "강한 1등 몰빵" 규칙. 수량 차이로 원치 않는 편향 생기면 Phase B 완료 후 재검토 |
| **배치 속도 부족으로 19:40 재평가 못 맞춤** | Phase H를 C/D보다 먼저 완료하거나 병렬. Phase C에서 90초 목표 미달성이면 블록 |
| **장후 4시간 새 악재 유입** | Phase D의 4축 브리핑 + material_news_count 감시 |
| **정적 NXT 리스트 지연** | 주 1회 월요일 새벽 갱신 배치. 7일 미갱신이면 배지 회색 + Slack 경고 |
| **키움 API 일시 장애** | 재시도 5회 후 paper mode 전환 + Slack 긴급 알림. 당일 주문 스킵 |
| **수급단타왕 N값/기준값 과적합** | Phase B 기본값은 보수적(N=3). Phase I에서 AB 테스트 |
| **-2% 칼손절이 백테스트와 안 맞음** | `trader_style` 기본값은 `default`(3%). scalper는 옵션 |
| **일일 -5% 한도 도달 후 당일 청산 문제** | -5% 도달해도 그 날 포지션은 8:00~09:00 정상 청산. 다음 날 신규 매수만 차단 |
| **이미 체결된 주문 취소 불가 상황** | 주문 상태 확인 루프가 발견 즉시 신규 주문 발주 중단 |

---

## 14. 오픈 이슈 / 사전 확인 필요

- [ ] **키움 개인 계좌 NXT 애프터마켓 자동 주문 가능 여부** — 소액 1주로 사전 테스트
- [ ] 키움 REST API `ka10080` 등이 15:40 이후~20:00 구간 NXT 호가·체결 데이터를 실제로 주는지 (현 `effective_venue`는 15:40 이후만 NXT로 보지만, 20:00 이후 재전환 로직 점검 필요)
- [ ] 키움 뉴스 API 범위 — 네이버 대비 누락 범주 확인 (있으면 해당 범주만 네이버 fallback)
- [ ] 미국 ES/NQ 선물 데이터 소스 — 키움 해외 API가 가능한지, 아니면 Yahoo/investing
- [ ] Slack 봇 등록 / 이메일 발송 경로 — 운영자 계정 연결
- [ ] "섹터 아주 강할 때" 정량 기준 초안: `sector_score=2 AND 각 종목 leader=2 AND 섹터 상승률≥5%` — Design에서 튜닝

---

## 15. SOP (운영자용 - 사람 개입 최소)

자동화 후 운영자가 해야 할 것은 매우 적다.

**평시 (매일)**
1. 09:10 Slack 전일 결과 리포트 확인 (체결/수익/kill switch 상태)
2. 배지 경고 있으면 원인 파악 (NXT 리스트 오래됨, 주문 실패 등)

**이상 감지 시**
1. 매수/매도 발주 Slack 알림 → 60초 내 `cancel` 응답으로 개별 주문 취소
2. Kill switch 즉시 중단: `.bkit/state/auto_trade_enabled` 파일에 `0` 저장
3. paper mode 자동 전환 알림 받으면 원인 파악 후 수동 복구

**주 1회 (월요일 아침)**
1. NXT 리스트 갱신 배치 결과 확인 (실패 시 수동 실행)
2. 주간 성과 리포트 확인

---

## 16. 참고 자료

### 16.1 내부

- `docs/CLOSING_BET_PRINCIPLES.md` — 기존 원칙 17장
- `batch/runtime_source/engine/generator.py`, `scorer.py`, `decision_policy.py`, `position_sizer.py`
- `batch/runtime_source/providers/kiwoom_client.py` — `effective_venue`, `venue_stock_code`
- `backend/app/services/closing_bet_service.py`, `performance_service.py`
- `backend/app/services/pick_selector.py`

### 16.2 외부

- [넥스트레이드 매매체결대상종목](https://www.nextrade.co.kr/transactionSys/content.do)
- [넥스트레이드 종가매매](https://www.nextrade.co.kr/menu/transactionStatusClosing/menuList.do)
- [신한투자증권 NXT 가이드](https://open.shinhansec.com/mobilealpha/html/CS/NXTPolicyGuide.html)
- [유안타증권 NXT 안내](https://www.myasset.com/myasset/static/trading/TR_1608001_T1.jsp)
- [KB증권 2026 1Q NXT 거래가능 종목](https://m.kbsec.com/go.able?linkcd=s060300010000&seq=10009354&idt=20251229)
- [한국투자증권 NXT 단계별 공지](https://m.koreainvestment.com/main/customer/notice/Notice.jsp?cmd=TF04ga000002&currentPage=1&num=44165)
- [나무위키 넥스트레이드](https://namu.wiki/w/%EB%84%A5%EC%8A%A4%ED%8A%B8%EB%A0%88%EC%9D%B4%EB%93%9C)
- [Newspim 고명환 인터뷰](https://www.newspim.com/news/view/20180214000050)
- [SLR클럽 수급단타왕 매매법](https://www.slrclub.com/bbs/vx2.php?id=free&no=37730151)

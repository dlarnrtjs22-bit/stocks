# NXT 자동매매 운영 가이드

작성일: 2026-04-22
대상: 운영자 본인
한 줄 요약: **uvicorn 하나만 살려두면 끝. 나머지는 `/자동매매 제어` UI에서 다 한다.**

---

## 1. 전체 구조

```
┌────────────────────────────────────────────────────────────────────┐
│  uvicorn (backend.app.main:app)  — 유일한 상주 프로세스             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  FastAPI 앱                                                  │  │
│  │  ├─ REST API (/api/closing-bet, /api/controls, /api/...)    │  │
│  │  ├─ SSE/폴링 엔드포인트                                      │  │
│  │  └─ 🧵 scheduler thread (백그라운드, 30초마다 시간 체크)     │  │
│  │       │                                                      │  │
│  │       ├─ 15:30  daily_candidate_extract                     │  │
│  │       ├─ 19:30  post_close_briefing                         │  │
│  │       ├─ 19:40  post_close_briefing (재평가)                │  │
│  │       ├─ 19:50  runner_buy (T1 40% / T2 30% / T3 30%)       │  │
│  │       ├─ 08:00  runner_sell (08:00~09:00:30 전체 플로우)    │  │
│  │       ├─ 09:10  daily_pnl_reconcile                         │  │
│  │       └─ 월 06:00  refresh_nxt_tickers                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
                         │
            상태 파일 (.bkit/state/)         키움 REST API
            ┌────────────────────┐      ┌────────────────────┐
            │ auto_trade_enabled │      │ api.kiwoom.com     │
            │ paper_mode         │      │ mockapi.kiwoom.com │
            │ trading_mode       │      │ appkey/secretkey   │
            │ disabled_jobs      │      └────────────────────┘
            └────────────────────┘
                         ▲
                         │
                         │ 읽기/쓰기
                         │
            ┌────────────────────────┐
            │  React UI              │
            │  /자동매매 제어 페이지 │
            │  (모든 토글, 상태표시) │
            └────────────────────────┘
```

### 핵심: 별도 서비스 설치 불필요
- scheduler는 **uvicorn의 백그라운드 쓰레드**로 상주
- uvicorn 살아있는 동안 자동으로 시간 맞춰 job fire
- 종료 시 scheduler 쓰레드도 같이 깔끔히 정리

---

## 2. 실행 방법

### 2.1 한 번만 — 프론트 빌드
```bash
cd C:\codex\stocks_new\frontend
npm run build
```
(앞으로 UI 수정 안 하면 다시 빌드할 필요 없음)

### 2.2 백엔드 기동 (한 번만. 항상 살려둘 것)
```bash
cd C:\codex\stocks_new
# 환경변수 PYTHONPATH 필요
$env:PYTHONPATH = "$PWD\.pydeps;$PWD"      # PowerShell
# export PYTHONPATH=".pydeps:$PWD"          # Linux/mac
uvicorn backend.app.main:app --host 127.0.0.1 --port 5056
```

기동 로그에서 다음 2줄 확인:
```
INFO scheduler: [scheduler] embedded thread starting
INFO scheduler: [scheduler] 7 jobs registered
```

### 2.3 UI 접속
브라우저: http://127.0.0.1:5056/  
사이드바 **자동매매 제어** 클릭.

---

## 3. UI 조작 (이것만 알면 됨)

### 3.1 상단 배지
| 배지 | 의미 |
|-----|------|
| 🟢 Scheduler 쓰레드 활성 | 백엔드 쓰레드 살아있음. 시간 되면 자동 fire |
| 🟡 Scheduler 쓰레드 비활성 | 백엔드 쓰레드 죽음. uvicorn 재시작 필요 |
| 🔴 실전투자 자동매매 활성화 중 | 진짜 돈으로 주문 나감. 주의! |

### 3.2 자동매매 스위치 카드

**Kill Switch (자동매매 활성화)**
- ON 해야 어떤 주문도 나감. OFF면 모든 주문 즉시 차단 (비상 정지).

**Paper Mode (모의 주문)**
- ON: 실제 주문 대신 감사 로그만 기록. 검증용.
- OFF: 실주문. Trading Mode에 따라 모의계좌 또는 실전계좌로.

### 3.3 거래 모드 카드

**모의투자 (MOCK)** / **실전투자 (REAL)** 2-button
- MOCK → `mockapi.kiwoom.com` 호출. 모의계좌 별도 키 필요. 키 미발급이면 실전 키 fallback → 401 예상.
- REAL → `api.kiwoom.com` 호출. 실전 계좌 + 실제 돈.

### 3.4 개별 Job 스케줄 카드

7개 job을 **개별적으로** on/off 가능:
| Job | 시간 | 용도 |
|-----|------|------|
| 15:30 후보 추출 | 15:30 | 매수할 Top 2 선정 |
| 19:30 장후 브리핑 | 19:30 | 4축 가드 체크 (뉴스/유동성/괴리/미국선물) |
| 19:40 재평가 | 19:40 | 교체 여부 최종 결정 |
| 19:50 자동매수 | 19:50 시작 | T1(40%)→T2(30%)→T3(30%) 단계적 발주 |
| 08:00 자동매도 | 08:00 시작 | 08:00~09:00:30 전체 플로우 |
| 09:10 일일 P/L 집계 | 09:10 | 수익률 집계 + 일일 -5% 손실한도 체크 |
| 월 06:00 NXT 갱신 | 월 06:00 | 800종목 리스트 갱신 |

예: "오늘만 매수 스킵" → 19:50 자동매수 OFF → 오늘 매수 안 나감, 내일부턴 다시 정상.

### 3.5 오늘의 Top 2 후보 / 장후 브리핑 / 주문 이력
10초마다 자동 새로고침. 읽기전용.

---

## 4. 타임라인 (하루 동안 일어나는 일)

```
이전 거래일 오후:
  15:10  ★ 기존 8 배치 전체 실행 (Run All)
          - Daily Prices / Institutional Trend / AI Analysis / Market Pulse
          - Program Trend / Intraday Pressure / VCP Signals / AI Jongga V2
          - LLM 5회 호출 포함. 약 2-5분 소요
          - 15:30 전에 jongga_signals 테이블에 저장 완료 목표
  15:30  ★ Top 2 추출 (candidate_set_v3 저장)
          - 15:10 run 결과를 DB에서 읽음. LLM 재호출 X
          - NXT 가능 + 매수 판정 종목 중 섹터 다양성 Top 2
  19:30  ★ 장후 브리핑 (2종목 LLM 재평가 포함)
          - 장후 4시간 신규 뉴스 확인, 유동성, 가격 괴리, 미국 선물
          - 2종목만 LLM 호출하므로 빠름
  19:40  ★ 재평가 (교체 여부 최종)
          - 19:45 이후 교체 금지 (주문 준비)
  19:50  ★ 매수 T1 — 매수1호가+1틱 지정가 40%
  19:54  ★ 매수 T2 — 현재가 지정가 30%
  19:58  ★ 매수 T3 — 매도1호가 지정가 30% (테이커, 체결 보장)

익일 새벽/오전:
  08:00  ★ 매도 S0 — 50% 현재가 지정가
  08:02  ★ 매도 S1 — 잔량 -1% 지정가
  08:04  ★ 매도 S2 — 잔량 -2% 지정가
  08:05  ★ 매도 S3 — 잔량 매수1호가 테이커
  08:06~08:49  ★ 1분마다 매수1호가 재조회 추격
  08:50  ★ NXT 프리마켓 종료. KRX 09시 동시호가 이관
  09:00:30  ★ NXT 메인 시장가 IOC 최종 잔량 청산
  09:10  ★ P/L 집계 + 일일 -5% 손실 한도 체크
```

### LLM 호출 전략
- **15:10 Run All 시**: 상위 상승 30개 종목에 LLM 뉴스 재료 분석 (기본 설정). `LLM_MAX_CALLS_PER_RUN=10` + `LLM_MAX_OVERALL_ANALYSIS=5` (overall 해설용).
- **15:30 Top 2 추출 시**: LLM 재호출 **없음**. DB에서 15:10 결과 그대로 읽음.
- **19:30 브리핑 시**: 2종목에 대해서만 장후 4시간 신규 뉴스 LLM 재평가 (빠름).
- 이유: 장중엔 종목 수가 많아 LLM 병목 → 장 마감 직전(15:10) 1회 처리. Top 2만 추려놓으면 브리핑은 2건만 재평가라 빠름.

★ 표시는 scheduler가 자동 실행.

---

## 5. 안전장치 (Design §9 Module G)

| 장치 | 파일 | 동작 |
|-----|------|------|
| Kill Switch | `.bkit/state/auto_trade_enabled` | 0 = 모든 주문 차단 (기본값) |
| Paper Mode | `.bkit/state/paper_mode` | 1 = 실주문 대신 로그만 (기본값) |
| Trading Mode | `.bkit/state/trading_mode` | `real` 또는 `mock` (기본 mock) |
| Disabled Jobs | `.bkit/state/disabled_jobs` | 한 줄에 하나씩 job 이름. 해당 job 스킵 |
| Daily -5% 차단 | `daily_pnl` 테이블 | 실현손실 -5% 도달 시 kill switch 자동 OFF |
| Paper 자동 전환 | `.bkit/state/consecutive_fail_count` | 3회 연속 실패 시 paper mode 자동 ON |
| 감사 로그 | `.bkit/audit/orders.jsonl` | 모든 주문 이벤트 append-only JSON |
| Slack 알림 | `SLACK_WEBHOOK_URL` env | 매 주문 발주 전 + 60초 취소 창 |

### 비상 정지 (UI 접근 불가 시)
```bash
# 1. Kill switch 즉시 OFF (다음 fire 때 체크됨, 이미 발주된 주문은 별도 취소 필요)
echo 0 > .bkit/state/auto_trade_enabled

# 2. 키움 앱에서 발주된 주문 수동 취소

# 3. (최후) 백엔드 프로세스 자체 종료
# Windows: 작업관리자에서 uvicorn 관련 python.exe 종료
# Linux: kill $(pgrep -f "uvicorn backend.app.main")
```

---

## 6. 첫 투입 절차 (권장)

### Step 1: 현재 안전 상태 유지 확인
UI 접속 후 다음 상태여야 함:
- Kill Switch: **OFF** (빨강, 비활성)
- Paper Mode: **ON** (초록, 활성)
- Trading Mode: **MOCK** (파랑)

→ 이 상태면 절대 실주문 안 나감.

### Step 2: Paper 모의 주문으로 흐름 검증
Kill Switch **ON** 전환. 나머지 그대로.  
= Kill Switch ON + Paper ON + Mode MOCK

다음 fire 시점(예: 내일 15:30)에:
- scheduler가 깨어남
- daily_candidate_extract 실행 (DB에 Top 2 저장)
- UI Top 2 카드에 후보 나타남
- 19:30/19:40 브리핑 실행 → UI 브리핑 카드에 4축 결과
- 19:50~58 **Paper** BUY 주문 발주 → UI 주문 이력에 `PAPER` 배지로 표시
- 익일 08:00~ **Paper** SELL 주문
- 09:10 집계

**실돈 1원도 안 나감**. 그냥 로그·DB 기록만 남는다.

### Step 3: 모의투자 실주문 (mockapi.kiwoom.com)
Paper Mode **OFF** 전환. 나머지 그대로.  
= Kill Switch ON + Paper OFF + Mode MOCK

⚠️ **모의투자 별도 appkey/secretkey 발급 필요**:
- 키움 openapi 포털에서 모의투자 신청
- 발급된 키를 `58416417_appkey_mock.txt` / `58416417_secretkey_mock.txt`에 저장
- 이 파일이 없으면 자동으로 실전 키 fallback → mockapi 401 예상

키 발급됐으면 mockapi에서 실제 주문 프로토콜 검증 가능. 모의계좌라 돈 안 나감.

### Step 4: 실전 투입
Trading Mode **REAL** 전환.  
= Kill Switch ON + Paper OFF + Mode REAL

빨간 경고 배너 뜸:
> 🔴 실전투자 자동매매 활성화 중 — 실제 돈으로 주문이 나갑니다.

이 시점부터 진짜 돈으로 주문 나감. 예수금 200만원 한도 내에서.

---

## 7. 상태 조회 (CLI, UI 말고)

### 상태 한 줄 요약
```bash
curl -s http://localhost:5056/api/controls/status | python -X utf8 -m json.tool
```

### 오늘 주문 이력
```bash
curl -s http://localhost:5056/api/controls/orders/today | python -X utf8 -m json.tool
```

### Top 2 / 브리핑
```bash
curl -s http://localhost:5056/api/controls/candidates/top2
curl -s http://localhost:5056/api/controls/briefing
```

### 감사 로그 tail
```bash
tail -f .bkit/audit/orders.jsonl
```

---

## 8. 배포 아키텍처 요약

**이상적인 배포**
- 1개 서버 / 1개 uvicorn 프로세스
- uvicorn이 부팅 시 자동 시작 (Windows 작업 스케줄러 / Linux systemd)
- 나머지 모든 것은 UI에서 제어

**별도 설치 필요한 것**
- (선택) uvicorn 자체 자동시작 — 서버 재부팅 대비
- (선택) Slack webhook URL — 발주 알림 원할 때

**별도 설치 불필요한 것**
- ~~NSSM~~ → scheduler가 uvicorn에 내장됨
- ~~Task Scheduler~~ → 위와 동일
- ~~systemd (scheduler용)~~ → 위와 동일
- ~~Redis~~ → in-memory TTL 캐시만 씀
- ~~별도 워커/큐~~ → subprocess로 각 job 실행

---

## 9. 트러블슈팅

| 증상 | 원인 | 해결 |
|-----|------|------|
| UI "Scheduler 쓰레드 비활성" | uvicorn 재시작 후 lifespan 오류 | 로그에서 traceback 확인, 필요 시 재기동 |
| 15:30 됐는데 Top 2 안 나타남 | kill switch OFF / extract job OFF / DB 오류 | UI 상태 확인, scheduler 로그 (`runtime/logs/scheduler.log`) |
| 주문 다 `FAILED: price_resolve_fail` | 호가 조회 0 반환 (장외 시간 등) | 장중에만 실행하도록 job 시간 유지. 비상 시 해당 종목 job OFF |
| 주문 다 `PAPER` 배지 | paper_mode=1 | UI에서 Paper Mode OFF |
| 모의 주문 시 401 Unauthorized | mock 키 미발급 | 키움 모의투자 신청 후 `58416417_*_mock.txt` 저장 |
| 백엔드 재시작 후 오늘 job 재실행? | `last_run_date`가 메모리에 있어 재시작 시 리셋 | 그래도 시간이 지나면 해당 분에만 fire. 이미 지난 분은 스킵 |

---

## 10. 파일 위치 참조

| 종류 | 경로 |
|-----|------|
| 백엔드 진입점 | `backend/app/main.py` |
| Scheduler 로직 | `batch/runtime_source/scheduler.py` |
| Control API | `backend/app/api/routes/controls.py` |
| Control UI | `frontend/src/pages/ControlPage.tsx` |
| 주문 래퍼 | `batch/runtime_source/providers/kiwoom_order.py` |
| TradeExecutor | `batch/runtime_source/executor/trade_executor.py` |
| Guards | `batch/runtime_source/executor/guards.py` |
| Runner (매수) | `batch/runtime_source/executor/runner_buy.py` |
| Runner (매도) | `batch/runtime_source/executor/runner_sell.py` |
| 상태 파일 | `.bkit/state/` |
| 감사 로그 | `.bkit/audit/orders.jsonl` |
| Scheduler 로그 | `runtime/logs/scheduler.log` |
| 키움 키 | `58416417_appkey.txt`, `58416417_secretkey.txt` (실전) / `*_mock.txt` (모의) |
| 설계 문서 | `docs/02-design/features/nxt-closing-bet-v2.design.md` |

---

## 11. 첫 실전 사이클 — 단계별 관찰 가이드

`/자동매매 제어`에서 **Kill Switch ON + Paper OFF + Trading Mode REAL** 로 전환한 날.
그날의 타임라인과 각 시점 확인 포인트.

| 시각 (KST) | 이벤트 | 정상 동작 확인 |
|-----------|--------|---------------|
| **15:10** | `batches-run-all` 자동 fire | Data Status 페이지에서 8 배치가 순차 RUNNING → OK. 5분 내 완료 |
| **15:30** | `extract` 자동 fire | `/자동매매 제어` "오늘의 Top 2 후보" 카드에 종목 나타남. 비어있으면 **STALE_SKIP 빨간 배너** — 15:10 Run All 미완료/실패. Data Status에서 수동 Run All 후 `python -m batch.runtime_source.pipelines.daily_candidate_extract` 재실행 |
| 15:30~19:30 | 장후 대기 | 개입 불필요. 사이트 닫아둬도 백엔드 scheduler가 알아서 |
| **19:30** | 1차 브리핑 | 브리핑 카드에 4축 배지 (뉴스/유동성/괴리/미국선물). action 주목: `KEEP` 정상 / `QTY_HALF` 수량 절반 / `DROP` 매수 스킵 |
| **19:40** | 2차 재평가 | 종목 교체 가능한 마지막 시점. 19:45 이후엔 교체 금지 |
| **19:50** | **T1 매수 40% 발주 (실전!)** | 주문 이력 카드에 `BUY T1` 녹색. 지정가 = 매수1호가 + 1틱 (메이커). 미체결 정상 |
| **19:54** | T2 30% (현재가 지정가) | 중립 공격성 |
| **19:58** | T3 30% (매도1호가 테이커) | **반드시 체결 보장**. 19:59 시점에 T1/T2/T3 모두 `FILLED` 또는 `PARTIAL` 상태여야 |
| (밤) | 대기 | 익일 매도까지 개입 불필요 |
| **08:00** | 매도 S0 — 현재가 50% | 주문 이력에 `SELL S0-initial50%` |
| **08:02** | S1 — 잔량 -1% 지정가 | 하향 추격 시작 |
| **08:04** | S2 — 잔량 -2% | 더 공격적 |
| **08:05** | S3 — 매수1호가 테이커 | 즉시 체결 지향 |
| 08:06~08:49 | 1분 간격 매수1호가 재발주 | 잔량 있으면 계속 추격 |
| **08:50** | NXT 프리 종료 | 잔량 있으면 KRX 09:00 동시호가 이관 |
| **09:00:30** | 최종 시장가 IOC | **반드시 잔량 0** |
| **09:10** | `reconcile` 자동 fire | `daily_pnl` 테이블 기록. 일일 -5% 도달 시 다음날 kill switch 자동 OFF |

### 첫 사이클 관찰 포인트

**15:30 확인**
- Top 2 카드에 종목 떴음? 안 뜨면 STALE 경고 → Run All 수동 재실행 필요
- 선정된 종목이 기대와 맞나? (상승률·뉴스 가진 주도주인지 확인)

**19:30 브리핑 확인**
- 유동성 `THIN` 경고 있나? → QTY_HALF로 수량 절반 감축됨
- 미국 선물 `-1%` 이상 하락? → 전체 DROP 됨
- 뉴스 `DETERIORATED` ? → 해당 종목 DROP

**19:50~59 매수 중 확인**
- 발주 직전 60초 취소 창 — Slack 알림 받으면 `touch .bkit/state/cancel_signal` 로 즉시 취소 가능
- 모든 tranche가 5분 내 FILLED 되면 OK
- 19:59까지 PENDING 있으면 T3 테이커 가격 재점검 (호가 갭 큼)

**08:00~09:00:30 매도 중 확인**
- 08:05까지 매도 진행률 70% 이상이면 순조
- 긴급 손절 스레드가 `-3% 이상 급락` 감지 시 즉시 BID1 전량 발주 (로그 확인)

**09:10 이후 일일 결산**
- `/자동매매 제어` 오늘 자동주문 이력 카드에서 매수/매도 전량 FILLED 확인
- `daily_pnl` 테이블에서 수익률 확인 (DB 직접 또는 나중에 UI 추가)

### 비상 정지 (첫 사이클 중 뭔가 이상할 때)

```
[UI 원클릭]
  /자동매매 제어 → Kill Switch OFF

[CLI 즉시]
  echo 0 > .bkit/state/auto_trade_enabled
```

**주의**: Kill Switch OFF는 "다음 fire 시점" 부터 차단. **이미 발주된 주문은 키움 앱에서 수동 취소** 필요.

### 첫 사이클 후 체크리스트

- [ ] 매수 3 tranche 모두 FILLED 확인
- [ ] 익일 매도 전량 FILLED (또는 09:00:30 이내 완료)
- [ ] daily_pnl 기록 정상
- [ ] Slack 알림 수신 (발주/체결)
- [ ] 감사 로그 `.bkit/audit/orders.jsonl` 무결성

문제 있으면 Paper Mode ON 으로 돌려서 재검증 → 원인 파악 → 재투입.

---

## 12. 한 줄 요약

```
uvicorn backend.app.main:app --port 5056 → 브라우저 /자동매매 제어 → UI에서 다 함.
```

Kill Switch / Paper Mode / Trading Mode / 각 Job on-off 모두 UI 토글.  
CLI 개입은 "UI 접근 불가 시 비상 정지" 용도로만.

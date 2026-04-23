# Plan: UI Modern Overhaul (Trading Pro)

- **Feature**: `ui-modern-overhaul`
- **Phase**: Plan
- **Created**: 2026-04-21
- **Owner**: gsim
- **PDCA Status**: Plan → Design → Do → Check → Act

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 현재 UI가 "구닥다리"로 느껴지고, 카드 위주 레이아웃·과도한 그라데이션·큰 라운드 코너로 **사용프로그램이 아닌 웹사이트 느낌**을 준다. 숫자 포매터가 존재하지만 화면마다 `toLocaleString`과 혼용되어 **표시 규칙이 제각각**이며, 외인/기관 숫자 색상이 부호와 무관하게 고정되는 등 **자잘한 버그**가 누적돼 있다. |
| **Solution** | **Trading Pro 스타일**(Bloomberg/TradingView 레퍼런스)로 5개 화면을 전면 재개편. **TailwindCSS + CSS Variables 디자인 토큰**으로 CSS 아키텍처 재구성. **문맥별 숫자 포맷 규칙**을 `formatters.ts`에 통일하고, 버그 오디트 결과 17건을 이번 사이클에서 일괄 해결. |
| **Function / UX Effect** | 데이터 밀도 상승(화면당 +40% 정보량), 숫자 정렬/정체성 일관, 한국식 등락 색상(빨강↑ / 파랑↓), 모노스페이스 숫자 폰트로 **프로 트레이딩 툴 체감**. 테이블 중심 레이아웃으로 스캔 속도 향상. |
| **Core Value** | "웹사이트"에서 "**전문 데스크톱 트레이딩 앱**"으로의 정체성 전환. 한 번의 사이클로 디자인 시스템과 화면을 동시 교체해 향후 기능 추가·유지보수 속도가 2배 이상 빨라진다. |

---

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | 현재 디자인이 구식이고 숫자/버그가 혼재해, 사용자가 국내 주식 종가배팅 의사결정 도구로서 신뢰하기 어렵다. |
| **WHO** | 이 프로젝트의 단일 사용자(owner) — 국내 주식 종가배팅 전략을 운용하는 개인 투자자 / 개발자 본인. |
| **RISK** | (1) Vanilla CSS 789줄 → Tailwind 전환 중 시각적 회귀, (2) 숫자 규칙 변경이 기존 리포트/로직에 영향, (3) 한 번에 5화면을 모두 바꾸는 범위 리스크. |
| **SUCCESS** | ① 5개 화면 Trading Pro 스타일 적용 완료, ② `fmtNumber` 외 모든 원시 `toLocaleString` 제거, ③ 버그 오디트 17건 모두 해결, ④ 빌드 통과 + 다크 테마 일관성. |
| **SCOPE** | **In**: 프론트엔드 UI 전면, Tailwind 도입, 디자인 토큰, formatters 재정리, 5개 화면 재구현, 버그 수정. **Out**: 백엔드 API 변경, 새 데이터 필드 추가, 인증/권한 변경, 모바일 반응형 풀 지원(최소 1440px 기준만). |

---

## 1. Overview

### 1.1 배경

`stocks_new`는 `REBUILD_PLAN.md`(2026년 초)에 따라 이미 백엔드·조회 구조를 재구축한 프로젝트다. 백엔드 아키텍처(FastAPI + read model + pool)는 안정화되었고, 최근 커밋은 계좌 내역/NXT/매매내역 등 기능 추가에 집중되었다. **그러나 UI는 기능 추가만 누적되어 일관성이 무너졌다** — 카드 기반 레이아웃에 테이블이 덧붙고, 789줄의 글로벌 CSS에 클래스들이 중복·재활용되며, 숫자 포매터 `formatters.ts`는 만들어놓고도 화면마다 우회해 `value.toLocaleString('ko-KR')`를 직접 호출한다.

### 1.2 현재 증상

- **시각적으로 옛날 느낌**: 24px 라운드 코너, 과한 그라데이션 배경, 과도한 카드 여백, 둥근 버튼(16px radius) — 소비자 SaaS 스타일이 트레이딩 툴에 어울리지 않음
- **숫자 표시 혼란**: Dashboard는 `fmtWon`, Performance는 `toLocaleString`, ClosingView는 `fmtWonToEok`, 곳곳에 원/억/K/M 혼용
- **정보 밀도 부족**: Dashboard 1종목 카드가 화면 절반 차지, 스캔 불가
- **버그 누적**: 부호 무관 색상 고정, 카운트 오류가 있는 grid 클래스 등

### 1.3 목표

이번 PDCA 사이클에서 달성할 것:

1. **디자인 정체성 전환**: 웹사이트 → Trading Pro 데스크톱 앱
2. **CSS 아키텍처 현대화**: 글로벌 vanilla CSS → TailwindCSS + CSS Variables 토큰
3. **숫자 규칙 통일**: 문맥별 규칙을 `formatters.ts`에 집약, 원시 `toLocaleString` 금지
4. **버그 오디트 17건 해결**: 아래 Section 6 리스트 참조

---

## 2. Requirements

### 2.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | 5개 화면(Dashboard / 매매내역 / 종가배팅 / 누적 성과 / Data Status) 전면 재구현 | P0 |
| FR-02 | TailwindCSS v3+ 도입, `tailwind.config.ts`에 디자인 토큰(컬러/스페이스/타이포) 정의 | P0 |
| FR-03 | 다크 테마 유지, CSS Variables로 색상/간격 토큰 노출 | P0 |
| FR-04 | 문맥별 숫자 포맷 규칙 확정 및 `formatters.ts` 통일 (아래 §4 참조) | P0 |
| FR-05 | 한국식 등락 색상: 상승=`#ff4d4f`(빨강), 하락=`#4096ff`(파랑), 보합=`#9ca3af` | P0 |
| FR-06 | 모노스페이스 숫자 폰트 적용 + `tabular-nums` 활성화 | P0 |
| FR-07 | 테이블 중심 레이아웃 전환 (카드는 요약/시그니처 영역에만 유지) | P0 |
| FR-08 | 사이드바 재설계 (집약형 내비, 아이콘+레이블) | P1 |
| FR-09 | 키보드 네비게이션 기본 지원 (탭 순서, Escape 닫기) | P1 |
| FR-10 | 버그 오디트 17건 모두 해결 (§6 참조) | P0 |

### 2.2 Non-Functional Requirements

| ID | 요구사항 | 기준 |
|----|----------|------|
| NFR-01 | 빌드 통과 | `npm run build` 성공 |
| NFR-02 | 최소 해상도 지원 | 1440×900 (데스크톱 우선, 모바일 out-of-scope) |
| NFR-03 | 초기 번들 크기 | gzip 기준 현재 + 30% 이내 |
| NFR-04 | 색맹 고려 | 등락은 색상 외에 `▲/▼` 기호 병행 |
| NFR-05 | 유지보수성 | 글로벌 CSS 50줄 이하로 축소, 나머지는 Tailwind/컴포넌트 범위 |

### 2.3 Out of Scope (명시적 제외)

- 백엔드 API 변경, DB 스키마 변경, 새 데이터 필드
- 라이트 테마 지원 (다크 전용)
- 모바일/태블릿 반응형 풀 지원
- 다국어 지원 (한국어 고정)
- 차트(시세 차트) 신규 도입

---

## 3. Design Direction: Trading Pro

### 3.1 스타일 정체성

**레퍼런스**: Bloomberg Terminal, TradingView, Interactive Brokers TWS

| 요소 | Before | After |
|------|--------|-------|
| 배경 | 라디얼 그라데이션 + 블루 하이라이트 | 단색 #0b0f17 (차분한 뉴트럴 다크) |
| 카드 라운드 | 18~24px | 6~8px |
| 카드 그림자 | `box-shadow: 0 18px 40px ...` | 거의 없음 (경계선 1px) |
| 버튼 라운드 | 16px | 4~6px |
| 버튼 높이 | 48px | 32~36px |
| 여백 | 16~28px | 8~12px |
| 폰트(숫자) | Segoe UI (프로포셔널) | JetBrains Mono / IBM Plex Mono (tabular) |
| 폰트(UI) | Segoe UI / Noto Sans KR | Inter / Pretendard |
| 주요 레이아웃 | 카드 나열 | 헤더 + 테이블 + 사이드 패널 |

### 3.2 컬러 토큰

```
--bg-base:        #0b0f17   /* 본문 배경 */
--bg-surface:     #121826   /* 카드/패널 */
--bg-elevated:    #1a2236   /* 호버/활성 */
--border-subtle:  #1f2a40
--border-default: #2a3652
--text-primary:   #e7ecf5
--text-secondary: #9aa6bd
--text-muted:     #5d6a82
--accent-up:      #ff4d4f   /* 한국식: 상승 = 빨강 */
--accent-down:    #4096ff   /* 한국식: 하락 = 파랑 */
--accent-flat:    #9ca3af
--accent-brand:   #3b82f6   /* 브랜드 블루 (버튼/링크) */
--accent-warn:    #fbbf24
--accent-grade-a: #f87171
--accent-grade-b: #fb923c
--accent-grade-c: #facc15
--accent-grade-d: #94a3b8
```

### 3.3 타이포그래피 토큰

```
--font-ui:     'Pretendard', 'Inter', -apple-system, sans-serif
--font-mono:   'JetBrains Mono', 'IBM Plex Mono', 'SF Mono', monospace
--text-xs:     11px  (라벨, 캡션)
--text-sm:     12px  (테이블 셀, 메타)
--text-base:   13px  (본문 기본)
--text-md:     14px  (섹션 타이틀)
--text-lg:     16px  (페이지 타이틀)
--text-xl:     20px  (주요 KPI)
--text-2xl:    28px  (히어로 숫자)
```

숫자는 모두 `font-variant-numeric: tabular-nums` 강제.

### 3.4 스페이싱/레이아웃

- 그리드 단위: 4px
- 카드 내부 패딩: 12px
- 페이지 여백: 16px (기존 28px 대비 축소)
- 테이블 셀 패딩: 6px × 10px
- 사이드바 폭: 220px (기존 280px 대비 축소)

---

## 4. 숫자 표시 규칙 (Number Format Spec)

### 4.1 규칙 매트릭스

| 맥락 | 예시 값 | 표시 | 함수 |
|------|--------|------|------|
| 주가 (원) | 72,500 | `72,500` (단위 생략) | `fmtPrice(v)` |
| 금액 - 대금/평가금액 (수십억+) | 3,204,500,000 | `32.0억` | `fmtMoneyEok(v)` |
| 금액 - 소액 (천만원대) | 12,400,000 | `1,240만` | `fmtMoneyAuto(v)` |
| 금액 - 작은 값 (만원 미만) | 4,500 | `4,500원` | `fmtMoneyAuto(v)` |
| 손익 (부호) | +1,240,000 | `+124만` 또는 `+1,240,000` | `fmtSignedMoney(v)` (맥락 옵션) |
| 수익률/% | 2.456 | `+2.46%` (부호 포함, 소수 2자리 고정) | `fmtSignedPercent(v)` |
| 수량/개수 | 12345 | `12,345` | `fmtCount(v)` |
| 점수 | 18 / 22 | `18/22` | 인라인 |
| 프로그램 매매 (±억) | -450,000,000 | `-4.5억` | `fmtSignedEok(v)` |
| 외인/기관 순매수 (부호) | +120,000,000 | `+1.2억` | `fmtSignedEok(v)` |
| 날짜 | 2026-04-21 | `2026-04-21` | `fmtDate(v)` |
| 일시 | — | `04-21 14:30:12` | `fmtDateTime(v)` |
| 시각 (HH:MM) | — | `14:30` | `fmtTimeHm(v)` |

### 4.2 통일 원칙

1. **맥락 명시**: 함수명에 단위/부호 여부가 드러나야 함 (`fmtMoneyEok`, `fmtSignedPercent`)
2. **영문 축약 제거**: `K/M/B` 사용 금지 → 한국식 `만/억/조`로 통일
3. **소수점 고정**: 퍼센트는 소수 2자리 고정, 억 단위는 소수 1자리, 그 외는 정수
4. **부호 강제**: `fmtSignedXxx` 계열은 항상 `+` 또는 `-` 표기 (0도 `+0` 또는 단순 `0`)
5. **`toLocaleString` 직접 호출 금지**: 모든 숫자 출력은 `formatters.ts`를 경유
6. **lint 규칙**: ESLint 커스텀 룰 또는 grep 검사로 강제

### 4.3 색상 규칙 (§3.2와 연동)

```
값 > 0  → text-[var(--accent-up)]    + "▲" 기호 선택적 표시
값 < 0  → text-[var(--accent-down)]  + "▼" 기호 선택적 표시
값 = 0  → text-[var(--accent-flat)]
```

**부호에 따른 자동 색상**이 핵심 — 현재 ClosingView가 "외인=항상 빨강, 기관=항상 초록"으로 잘못 구현된 버그를 fix.

---

## 5. 페이지별 변경 계획

### 5.1 Dashboard (`DashboardPage.tsx`)

**Before**: 커다란 카드 5개를 세로로 나열, 각 카드 안에 4×N 메트릭 그리드 + 리포트 본문
**After**:
- 상단 고정 **시장 스트립**: KOSPI/KOSDAQ/코넥스 가로 1줄, 지수·변화율·상승/하락 수·프로그램 금액
- 좌측 **추천 5종목 테이블** (grade/name/ticker/price/%/score/decision)
- 우측 **선택 종목 상세 패널** (선택 시 리포트·근거·키포인트 표시) — 마스터/디테일 구조
- 하단 **업데이트 시각 바**

### 5.2 매매내역 (`TradeHistoryPage.tsx`)

**Before**: 4+4 메트릭 그리드 → 보유종목 테이블 → 일자별 손익 테이블 → 15열 체결내역 테이블(오버플로우)
**After**:
- 상단 **계좌 KPI 바** (평가금액·평가손익·실현손익·보유종목 — 가로 1줄, 숫자 크게)
- **탭 전환** (`보유` / `일자별` / `체결`) — 한 화면에 3개 테이블 공존 제거
- 체결 테이블 컬럼 축소(venue 중복 제거), 수평 스크롤 허용, sticky header
- 손익 셀은 부호 색상 자동 적용

### 5.3 종가배팅 (`ClosingBetPage.tsx`)

**Before**: Featured 5 카드 + 전체 후보 카드 나열 (카드당 화면 2/3)
**After**:
- **메인 테이블**: 등급/종목/점수/가격/%/거래대금/결정 — 한 화면에 20종목 스캔 가능
- 선택 행 **상세 드로어**: AI 분석 + 점수 분해 + 뉴스 + 컨텍스트
- "Featured 5"는 테이블 상단에 시그니처 배지로 강조 (별도 그리드 제거)
- 점수 바 width 버그(`value * 34`) 수정 → `value / scoreMax * 100`

### 5.4 누적 성과 (`PerformancePage.tsx`)

**Before**: 4 KPI + 4 등급 카드 + 11열 테이블
**After**:
- 상단 **KPI 스트립** (Total / 08시 승률 / 09시 승률 / Edge)
- **등급별 성과 테이블**화 (카드 → 1줄당 1등급, 08/09 가로 비교)
- 메인 거래 테이블: 컬럼 정리, outcome pill 크기 축소, `formatPrice` 0원 버그 수정
- 비교값 갱신 버튼을 테이블 우상단으로 이동

### 5.5 Data Status (`DataStatusPage.tsx`)

**Before**: 배치 상태 뷰 (`BatchStatusView.tsx`)
**After**:
- 배치 상태 **그리드 뷰** (4열 × N행, 각 셀: 배치명/상태 뱃지/최근 실행/지속시간)
- 로그는 하단 collapsible 패널 (초기 접힘)
- 상태 뱃지 컬러 토큰화 (success/running/failed/idle)

---

## 6. 버그 오디트 (17건)

### 6.1 Critical (동작/정확성)

| # | 파일 | 증상 | 수정 방향 |
|---|------|------|-----------|
| B-01 | `ClosingView.tsx:66,70,74,78` | 외인=항상 `accent-danger`(빨강), 기관=항상 `accent-success` — **값의 부호 무관하게 색상 고정** | 값 부호에 따라 up/down/flat 토큰 자동 적용 |
| B-02 | `ClosingView.tsx:114` | 점수 바 `width: value * 34%` — 매직 넘버, 점수 max에 종속되지 않음 | `width: (value / scoreMax) * 100%` |
| B-03 | `PerformanceView.tsx:24` | `formatPrice(0)` → `'-'`로 표시 (falsy 버그, 0원은 `'-'`가 아님) | `value == null ? '-' : fmtPrice(value)` |
| B-04 | `DashboardView.tsx:90` | `metric-box-row four` 클래스에 메트릭 6개 배치 — grid overflow | 3열 또는 6열로 재지정 |
| B-05 | `ClosingView.tsx:59` | `metric-box-row three` 클래스에 메트릭 5개 배치 | 5열 또는 3+2로 재지정 |

### 6.2 Important (UX/일관성)

| # | 파일 | 증상 | 수정 방향 |
|---|------|------|-----------|
| B-06 | `TradeHistoryView.tsx:164,170` | 체결내역 테이블에서 `venue`가 2번 표시 (체결시각 하단 + 전용 컬럼) | 전용 컬럼 하나만 남김 |
| B-07 | `TradeHistoryView.tsx:140-157` | 체결 테이블 15개 컬럼 — 1440px에서도 오버플로우 | 컬럼 축소 + 수평 스크롤 |
| B-08 | `DashboardView.tsx:112` | 라벨 "호출 거래소" — 의미 불명 (아마 "호가 거래소"의 오타) | "거래소"로 통일 또는 실제 의미로 수정 |
| B-09 | `DashboardView.tsx:19` | `accountRefreshing` 구조분해만 하고 미사용 | 사용하거나 제거 |
| B-10 | `DashboardView.tsx:9` | `onRefreshAccount` prop 선언되었으나 호출 없음 | 제거 또는 UI 버튼 연결 |
| B-11 | `PerformanceView.tsx:24,93` | `value.toLocaleString('ko-KR')` 직접 호출 — formatters 우회 | `fmtPrice/fmtCount` 경유 |
| B-12 | `ClosingView.tsx` scoreLabels | `news_attention` 외 다수 키 누락 시 영문 키 노출 | 전 키 매핑 또는 안전한 fallback |

### 6.3 Minor (코드 품질)

| # | 파일 | 증상 | 수정 방향 |
|---|------|------|-----------|
| B-13 | `formatters.ts:71-89` | `fmtCompactSigned`가 K/M/B 영문 단위 사용 | 한국식 `만/억/조`로 교체 또는 deprecate |
| B-14 | `formatters.ts:48-63` | `fmtSigned`는 단위 없는 부호 숫자인데 가격/수량에 혼용 | `fmtPrice`, `fmtSignedCount` 등으로 명확 분리 |
| B-15 | `app.css` | 전체 `color-scheme: dark` 선언만 있고 라이트/다크 토큰 분리 없음 | CSS Variables 토큰화 |
| B-16 | `app.css` (789줄) | 클래스명 글로벌 오염 (`.closing-card`, `.dashboard-pick-card` 등) | Tailwind 전환 시 컴포넌트 범위로 이관 |
| B-17 | 전 테이블 | `font-variant-numeric: tabular-nums` 미적용 → 숫자 정렬 흔들림 | 전역 `.mono-num` 유틸 추가 |

---

## 7. Success Criteria

완료 판정 기준 (Check 단계에서 각 항목 ✅/❌ 체크):

| SC | 기준 | 측정 방법 |
|----|------|-----------|
| SC-01 | 5개 페이지 모두 Trading Pro 스타일 적용 | 육안 확인 + 시그니처 요소(단색 배경·8px 라운드·모노 숫자) 체크 |
| SC-02 | TailwindCSS 도입 및 빌드 통과 | `npm run build` 성공, `tailwind.config.ts` 존재 |
| SC-03 | `formatters.ts`가 모든 숫자 출력의 단일 경로 | `grep -r "toLocaleString" frontend/src` 결과 0건 (formatters.ts 자체 제외) |
| SC-04 | 한국식 등락 색상 적용 | 상승 빨강(#ff4d4f) / 하락 파랑(#4096ff) CSS 변수 기반 확인 |
| SC-05 | 모노스페이스 숫자 폰트 적용 | 숫자 영역에 `font-mono` 또는 `tabular-nums` 클래스 확인 |
| SC-06 | 버그 17건 해결 | §6 체크리스트 모두 ✅ |
| SC-07 | app.css 50줄 이하로 축소 | `wc -l frontend/src/styles/app.css` ≤ 50 |
| SC-08 | 디자인 토큰 정의 완료 | `tailwind.config.ts`에 color/spacing/typography 토큰 존재 |
| SC-09 | 1440×900 해상도에서 오버플로우 없음 | 각 페이지 스크린샷 확인 |
| SC-10 | 시각 회귀 없음 | 기존 기능(데이터 로딩/페이지네이션/탭 전환) 모두 동작 |

**최종 Match Rate 목표**: 90% 이상

---

## 8. Risks & Mitigations

| ID | 리스크 | 영향도 | 완화책 |
|----|--------|--------|--------|
| R-01 | Tailwind 도입 중 빌드 깨짐 | H | Do 단계 첫 세션에서 Tailwind 세팅 + `build` 통과 후 커밋 |
| R-02 | 한 번에 5화면 재개편 → 중간 상태에서 일부 화면 동작 불능 | M | 디자인 토큰·공통 컴포넌트 먼저 완성 → 페이지는 `AppShell`→`Dashboard`→... 순서로 차례 교체 |
| R-03 | 숫자 규칙 변경으로 기존 화면 회귀 | M | `formatters.ts` 변경 시 기존 함수는 deprecated 주석 후 일괄 치환, 테스트 화면 로딩 확인 |
| R-04 | 부호 기반 색상 자동화가 일부 특수 셀(손절가/목표가)에 의도치 않게 적용 | L | `fmtPrice`는 색상 미적용, 손익/퍼센트 계열만 부호 색상 자동화 |
| R-05 | 글로벌 `app.css` 제거 중 놓친 스타일 | M | grep 기반 클래스 사용처 전수 확인 후 제거 |
| R-06 | Pretendard/JetBrains Mono 폰트 로딩 실패 → 시스템 폰트로 fallback | L | `font-display: swap` + 시스템 폰트 대체 체인 명시 |

---

## 9. Dependencies & Prerequisites

- React 19.1 / Vite 7.1 / TypeScript 5.9 (현재 스택 유지)
- **신규 도입**:
  - `tailwindcss@^3.4`, `postcss`, `autoprefixer`
  - `@tailwindcss/forms` (선택)
  - `clsx` (이미 자체 구현됨, 계속 자체 유틸 사용 가능)
  - Pretendard 웹폰트 (CDN 또는 self-host)
  - JetBrains Mono 웹폰트
- **신규 폴더**:
  - `frontend/src/styles/tokens.css` (CSS Variables)
  - `frontend/src/components/ui/*` (공통 프리미티브: Button, Table, Panel, Badge, Tabs)

---

## 10. 구현 순서 (Do Phase Outline)

> Design 단계에서 세션 분할(--scope)로 세부 모듈화. 아래는 초안.

1. **M1: Foundation** — Tailwind 설정 + 디자인 토큰 + 폰트 로드 + `tokens.css`
2. **M2: Primitives** — 공통 컴포넌트 (Button, Panel, Table, Badge, Tabs, Tag, KpiStat)
3. **M3: formatters 리팩토링** — 새 함수 추가, 기존 호출부 일괄 치환, `toLocaleString` 박멸
4. **M4: AppShell 재구성** — 사이드바 집약, 헤더 라인 추가
5. **M5: Dashboard** — 마스터/디테일 구조, 시장 스트립
6. **M6: 종가배팅** — 테이블 + 드로어, 점수 바 수정
7. **M7: 누적 성과** — KPI 스트립 + 등급 테이블 + 메인 테이블
8. **M8: 매매내역** — KPI 바 + 탭 + 정돈된 체결 테이블
9. **M9: Data Status** — 배치 그리드 뷰 + 로그 패널
10. **M10: Bug sweep & polish** — §6 잔여 버그 + 시각 정돈 + 빌드 확인

---

## 11. Open Questions (Design 단계에서 확정)

- **Q1**: 테이블 행 호버/선택 색상은 `--bg-elevated` 한 가지로 통합할지, hover/selected 분리할지?
- **Q2**: Dashboard 마스터/디테일에서 디테일 패널의 폭 비율 (6:4 vs 7:3 vs 토글)?
- **Q3**: 사이드바에 아이콘 도입 시 아이콘 라이브러리 선택 (lucide-react 권장)?
- **Q4**: 등급 색상을 A/B/C/D 4단계로 고정할지, 실제 DB에서 나오는 등급 값 전부에 대응할지?
- **Q5**: 차트(점수 바 외)를 신규 도입할지 (현재 Out of Scope이나 Performance 화면에서 고려 여지)?

---

## 12. Next Phase

- **Design**: `/pdca design ui-modern-overhaul`
  - 3가지 아키텍처 옵션 제시
  - Module Map 및 Session Guide 생성
  - Design Anchor 연동 여부 결정
- 이후 순서: `/pdca do --scope M1,M2` → ... → `/pdca analyze` → `/pdca qa` → `/pdca report`

---

*Plan generated 2026-04-21 via `/pdca plan ui-modern-overhaul`.*

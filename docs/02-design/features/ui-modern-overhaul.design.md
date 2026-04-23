# Design: UI Modern Overhaul (Trading Pro)

- **Feature**: `ui-modern-overhaul`
- **Phase**: Design
- **Selected Architecture**: **Option C — Pragmatic Primitives**
- **Created**: 2026-04-21
- **Related Plan**: [ui-modern-overhaul.plan.md](../../01-plan/features/ui-modern-overhaul.plan.md)

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

### 1.1 Architecture Summary

**Option C: Pragmatic Primitives**를 채택한다.

- **핵심 프리미티브 9개**를 `frontend/src/components/ui/` 에 배치한다.
- 프리미티브 외 레이아웃/원샷 스타일은 Tailwind 유틸리티를 JSX에 직접 사용한다.
- 외부 UI 라이브러리(Radix, shadcn 등) 미도입 — `cva`(class-variance-authority)만 variant 관리용으로 선택적 도입한다.
- 모든 색상/스페이스/타이포 토큰은 **CSS Variables**로 `src/styles/tokens.css`에 선언하고, `tailwind.config.ts`가 이를 참조한다.

### 1.2 왜 Option C인가 (Trade-off 정리)

| 기준 | 판정 |
|------|------|
| 1인 트레이딩 앱 규모 | 전체 디자인 시스템(Option B)은 과함 |
| 유틸리티 반복 방지 | Option A는 `Num`, `Panel`, `DataTable` 반복 발생 |
| 속도 vs 품질 | 3-4세션으로 완료 가능, 장기 유지보수 양호 |
| 버그 B-01 자동 해결 | `<Num tone="auto">` 한 컴포넌트가 부호 기반 색상 자동 적용 → Critical 버그 구조적 차단 |

### 1.3 Directory Layout (After)

```
frontend/
  src/
    app/
      App.tsx
      formatters.ts          # 재정리됨
    api/
      client.ts
      endpoints.ts
    components/
      ui/                    # ★ 신규 — 9개 프리미티브
        Num.tsx
        Panel.tsx
        Badge.tsx
        DataTable.tsx
        KpiStat.tsx
        Tabs.tsx
        OutcomePill.tsx
        ScoreBar.tsx
        Drawer.tsx
      layout/
        AppShell.tsx         # 재작성
      dashboard/
        DashboardView.tsx    # 재작성 (마스터/디테일)
        PicksTable.tsx       # 신규 분리
        PickDetailPanel.tsx  # 신규 분리
        MarketStrip.tsx      # 신규 분리
      closing/
        ClosingView.tsx      # 재작성 (테이블 중심)
        ClosingTable.tsx     # 신규
        ClosingDetailDrawer.tsx # 신규
      performance/
        PerformanceView.tsx  # 재작성
        PerformanceTradeTable.tsx
        GradeSummaryTable.tsx
      trade-history/
        TradeHistoryView.tsx # 재작성 (탭 구조)
        PositionsTable.tsx
        DailyPnlTable.tsx
        ExecutionsTable.tsx
      batch/
        BatchStatusView.tsx  # 재작성 (그리드)
        BatchLogPanel.tsx
      common/
        Pager.tsx            # 유지 (스타일만 업데이트)
        Modal.tsx            # 유지 또는 Drawer로 대체
        BasisPanel.tsx       # 유지 (토큰 적용)
    pages/
      *.tsx                  # 유지 (얇은 컨테이너)
    styles/
      tokens.css             # ★ 신규 — CSS Variables
      tailwind.css           # ★ 신규 — @tailwind directives
      app.css                # ≤ 50 줄로 축소
    types/
      api.ts                 # 변경 없음
  tailwind.config.ts         # ★ 신규
  postcss.config.js          # ★ 신규
```

---

## 2. Design Tokens

### 2.1 Color Tokens (`src/styles/tokens.css`)

```css
:root {
  /* Surface */
  --bg-base:        #0b0f17;
  --bg-surface:     #121826;
  --bg-elevated:    #1a2236;
  --bg-row-hover:   #172035;

  /* Border */
  --border-subtle:  #1f2a40;
  --border-default: #2a3652;
  --border-strong:  #3d4d72;

  /* Text */
  --text-primary:   #e7ecf5;
  --text-secondary: #9aa6bd;
  --text-muted:     #5d6a82;
  --text-disabled:  #3d4a62;

  /* Korean market: red = up, blue = down */
  --accent-up:      #ff4d4f;
  --accent-up-bg:   rgba(255, 77, 79, 0.12);
  --accent-down:    #4096ff;
  --accent-down-bg: rgba(64, 150, 255, 0.12);
  --accent-flat:    #9ca3af;

  /* Interaction */
  --accent-brand:   #3b82f6;
  --accent-brand-hover: #2563eb;
  --accent-focus:   #60a5fa;

  /* Status */
  --accent-success: #22c55e;
  --accent-warn:    #fbbf24;
  --accent-danger:  #ef4444;
  --accent-info:    #38bdf8;

  /* Grade (종목 등급) */
  --grade-a: #f87171;
  --grade-b: #fb923c;
  --grade-c: #facc15;
  --grade-d: #94a3b8;

  /* Typography */
  --font-ui:   'Pretendard', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', 'IBM Plex Mono', 'SF Mono', Consolas, monospace;

  /* Radii */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;

  /* Shadows — minimal, flat design */
  --shadow-card: 0 0 0 1px var(--border-subtle);
  --shadow-elevated: 0 4px 12px rgba(0,0,0,0.3), 0 0 0 1px var(--border-default);
}
```

### 2.2 Tailwind Config 요약 (`tailwind.config.ts`)

```ts
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base: 'var(--bg-base)',
        surface: 'var(--bg-surface)',
        elevated: 'var(--bg-elevated)',
        'row-hover': 'var(--bg-row-hover)',
        border: {
          subtle: 'var(--border-subtle)',
          DEFAULT: 'var(--border-default)',
          strong: 'var(--border-strong)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
        },
        up: 'var(--accent-up)',
        down: 'var(--accent-down)',
        flat: 'var(--accent-flat)',
        brand: 'var(--accent-brand)',
        success: 'var(--accent-success)',
        warn: 'var(--accent-warn)',
        danger: 'var(--accent-danger)',
        grade: {
          a: 'var(--grade-a)',
          b: 'var(--grade-b)',
          c: 'var(--grade-c)',
          d: 'var(--grade-d)',
        },
      },
      fontFamily: {
        ui: 'var(--font-ui)',
        mono: 'var(--font-mono)',
      },
      fontSize: {
        xs: ['11px', '14px'],
        sm: ['12px', '16px'],
        base: ['13px', '18px'],
        md: ['14px', '20px'],
        lg: ['16px', '22px'],
        xl: ['20px', '26px'],
        '2xl': ['28px', '34px'],
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
      },
    },
  },
  plugins: [],
};
```

---

## 3. Core Primitives (9개)

### 3.1 `<Num />` — 숫자 렌더 단일 진입점 ★핵심

**목적**: 모든 숫자 표시를 이 컴포넌트로 경유 → 포맷·색상·폰트 일관성 자동.

```ts
interface NumProps {
  value: number | null | undefined;
  format: 'price' | 'percent' | 'count' | 'eok' | 'signed-eok' | 'signed-percent' | 'signed-count';
  tone?: 'auto' | 'neutral' | 'muted';   // default: 'neutral' for unsigned, 'auto' for signed
  decimals?: number;                      // override default decimals
  showArrow?: boolean;                    // ▲/▼ prefix
  className?: string;
}
```

**규칙 (Plan §4.1 매핑)**:

| format | 예시 |
|--------|------|
| `price` | `72,500` |
| `percent` | `2.46%` |
| `count` | `12,345` |
| `eok` | `32.0억` (우선순위 자동: ≥수십억=억, ≥천만원=만, <만원=원) |
| `signed-percent` | `+2.46%` |
| `signed-eok` | `+32.0억` |
| `signed-count` | `+1,234` |

**tone='auto'**: value>0 → `text-up`, value<0 → `text-down`, 그 외 `text-primary`
**언제나**: `font-mono`, `tabular-nums` 적용

이 한 컴포넌트가 **Plan §6 버그 B-01, B-03, B-11, B-13, B-14, B-17**을 구조적으로 해결한다.

### 3.2 `<Panel />` — 카드/섹션 컨테이너

```ts
interface PanelProps {
  tone?: 'default' | 'subtle' | 'elevated';  // 배경 단계
  padding?: 'none' | 'sm' | 'md' | 'lg';     // 내부 여백
  title?: React.ReactNode;                    // 헤더 타이틀
  action?: React.ReactNode;                   // 헤더 우측 버튼
  bordered?: boolean;                         // border 여부 (default true)
  children: React.ReactNode;
}
```

- `default`: `bg-surface`, border 1px
- `subtle`: `bg-base`, border only
- `elevated`: `bg-elevated`, shadow

### 3.3 `<Badge />` — 등급/상태 태그

```ts
interface BadgeProps {
  variant:
    | 'grade-a' | 'grade-b' | 'grade-c' | 'grade-d'
    | 'success' | 'warn' | 'danger' | 'info'
    | 'up' | 'down' | 'flat'
    | 'neutral';
  size?: 'xs' | 'sm';
  children: React.ReactNode;
}
```

예: `<Badge variant="grade-a">A 등급</Badge>`, `<Badge variant="up">BUY</Badge>`

### 3.4 `<DataTable />` — 테이블 래퍼

Trading Pro의 핵심. 직접 render prop 형태로 제공.

```ts
interface Column<T> {
  key: string;
  header: React.ReactNode;
  width?: string;                 // e.g. '80px', '1fr'
  align?: 'left' | 'right' | 'center';
  sticky?: 'left' | 'right';       // freeze column
  render: (row: T, index: number) => React.ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedKey?: string;            // 선택된 행 하이라이트
  emptyMessage?: string;
  dense?: boolean;                 // 더 조밀한 padding
  stickyHeader?: boolean;
}
```

**기본 동작**:
- `thead` sticky, `border-b`
- `tbody tr` hover: `bg-row-hover`, selected: `bg-elevated`
- 숫자 정렬은 `align="right"` + `<Num />` 조합
- 수평 스크롤은 부모가 wrapping (`<div className="overflow-x-auto">`)

### 3.5 `<KpiStat />` — 상단 KPI 블록

```ts
interface KpiStatProps {
  label: string;
  value: React.ReactNode;          // usually <Num />
  delta?: React.ReactNode;         // optional 부가 정보
  hint?: React.ReactNode;          // 작은 메타 텍스트
  tone?: 'default' | 'up' | 'down'; // 하이라이트 색상
}
```

레이아웃: label(작게, secondary) 위, value(크게, mono) 아래, delta/hint(아주 작게, muted) 최하단.

### 3.6 `<Tabs />` — 탭 컨테이너

```ts
interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  items: Array<{ value: string; label: string; count?: number }>;
  variant?: 'segmented' | 'underline';
}
```

외부 라이브러리 없이 자체 구현. Radio-like 키보드 네비(ArrowLeft/Right).

### 3.7 `<OutcomePill />` — 거래 결과 표시

```ts
interface OutcomePillProps {
  outcome: 'WIN' | 'LOSS' | 'OPEN' | 'PENDING';
  size?: 'xs' | 'sm';
}
```

- WIN → 한국식: 빨강 계열
- LOSS → 파랑 계열
- OPEN → 회색
- PENDING → 연한 warn

### 3.8 `<ScoreBar />` — 점수 바

```ts
interface ScoreBarProps {
  value: number;
  max: number;                     // 버그 B-02 해결: max 필수
  label?: string;
  compact?: boolean;
}
```

`width: (value / max) * 100%` 공식으로 정규화 — 매직 넘버 34 제거.

### 3.9 `<Drawer />` — 우측 슬라이드 패널 (상세 드로어)

```ts
interface DrawerProps {
  open: boolean;
  onClose: () => void;
  width?: 'md' | 'lg' | 'xl';      // 420/560/720px
  title?: React.ReactNode;
  children: React.ReactNode;
}
```

`role="dialog"`, Escape 닫기, 백드롭 클릭 닫기, focus trap(간단 구현).

---

## 4. Page-Level Design

### 4.1 AppShell (사이드바 + 메인)

```
┌───────────────┬────────────────────────────────────────────┐
│  MF           │ Dashboard                           [⟳]    │
│  MarketFlow   ├────────────────────────────────────────────┤
│  v0.2         │                                            │
│               │   (page content)                           │
│ □ Dashboard   │                                            │
│ □ 매매내역    │                                            │
│ □ 종가배팅    │                                            │
│ □ 누적 성과   │                                            │
│ □ Data Status │                                            │
│               │                                            │
│ ─────────     │                                            │
│ KR MARKET     │                                            │
│ 2026-04-21    │                                            │
│ Updated 14:30 │                                            │
└───────────────┴────────────────────────────────────────────┘
  220px              1fr
```

- 사이드바: 220px 고정, `bg-surface`, `border-r`
- 메뉴 항목: 패딩 8px 12px, 선택 시 좌측 2px 세로 바 + `bg-elevated`
- 상단 브랜드는 작게 (32px 뱃지 + 작은 텍스트)
- 하단 고정 영역: 시장 현재가 요약(옵션)

### 4.2 Dashboard — 마스터/디테일

```
┌─ Market Strip ────────────────────────────────────────────┐
│ KOSPI 2,612.45  ▲+0.82%  ···  KOSDAQ ···  KONEX ···       │
├─ 추천 후보 (5) ──────────────────┬─ 선택 종목 상세 ──────┤
│ 등급│ 종목   │ 티커 │ 현재가 │% │                        │
│  A  │ 삼성…  │00593 │72,500 │▲│ 삼성전자 (005930)      │
│  A  │ SK…   │00066 │ 185k  │▲│                        │
│  B  │ 포스코 │00532 │ 412k  │▼│ AI 리포트…             │
│  ...                             │ 키포인트…              │
└─────────────────────────────────┴────────────────────────┘
                                       8:4 비율
```

- 좌측(8): `PicksTable` — 압축 테이블, 클릭 시 우측 선택
- 우측(4): `PickDetailPanel` — 선택된 종목의 리포트/근거/키포인트

### 4.3 종가배팅 — 테이블 + 우측 드로어

```
┌─ 툴바 ───────────────────────────────────────────────┐
│ [Featured 5 표시] [검색...] [등급필터]    [페이지 1/12]│
├─ 메인 테이블 ────────────────────────────────────────┤
│ ★│등급│종목 │티커 │점수 │현재가 │%   │거래대금│결정  │
│ ★│ A  │...  │...  │18/22│72,500 │▲.. │32.0억  │ BUY  │ ← Featured 별표
│  │ A  │...  │...  │17/22│ ...   │... │...     │      │
│  ...                                                 │
└──────────────────────────────────────────────────────┘
  행 클릭 → 우측에서 Drawer 슬라이드 인 (560px)
  [상세 드로어: 가격/점수분해/AI분석/뉴스/컨텍스트]
```

- Featured 5는 ★ 컬럼으로 표시, 별도 그리드 없음
- 행 선택 시 Drawer 오픈
- 점수 바는 컴팩트 모드 (6px 높이)

### 4.4 누적 성과 — KPI 스트립 + 2개 테이블

```
┌─ KPI Strip (4 x KpiStat) ────────────────────────────┐
│ Total   │ 08시 승률   │ 09시 승률   │ 비교 (Edge)    │
│ 127     │ 62.5%       │ 58.3%       │ 08 NXT +4.2%p  │
├─ 등급별 성과 (grade summary table) ──────────────────┤
│ 등급│건수│08 승률 │08 평균 ROI │09 승률│09 평균 ROI│ │
│  A  │ 42 │ 71.4%  │  +1.85%    │ 66.7% │  +1.52%   │ │
│  ...                                                 │
├─ 거래 내역 테이블 ───────────────────────────────────┤
│ 등급│종목│티커│진입가│매수일│평가일│08평가│08 ROI│...│
│  ...                                                 │
└──────────────────────────────────────────────────────┘
```

- `formatPrice(0)` 버그 B-03 해결: `<Num value={price} format="price" />` 사용 (null만 '-')
- 비교값 갱신 버튼은 "거래 내역" 테이블 타이틀 옆으로

### 4.5 매매내역 — KPI 바 + 탭 3개

```
┌─ 계좌 KPI 바 ────────────────────────────────────────┐
│ 평가금액       평가손익       실현손익       추정자산 │
│ 12,450,000원  +230,000원     +1,450,000원  14,120,000│
├─ 메타 정보 ──────────────────────────────────────────┤
│ 계좌 58416417 / 갱신 04-21 14:30:12  [계좌 새로고침] │
├─ Tabs: [보유 종목] [일자별 손익] [체결 내역] ────────┤
│                                                      │
│  선택 탭에 해당하는 테이블만 표시                    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

- 3개 테이블이 동시에 보이지 않음 → 한 번에 하나씩
- 체결 테이블: 중복 venue 컬럼 제거 (B-06), 컬럼 10~11개로 축소 (B-07)
- 수평 스크롤 허용 (overflow-x-auto)

### 4.6 Data Status — 배치 그리드

```
┌─ 배치 상태 그리드 (auto-fit, min 260px) ─────────────┐
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│ │ collect_ohlc│ │ collect_...│ │ signal_gen  │     │
│ │ [SUCCESS]   │ │ [RUNNING]  │ │ [SUCCESS]   │     │
│ │ 04-21 13:00│ │ 04-21 14:20│ │ 04-21 14:25 │     │
│ │ 2.3s        │ │ 00:12s 진행│ │ 5.1s        │     │
│ └─────────────┘ └─────────────┘ └─────────────┘     │
│ ...                                                 │
├─ 로그 패널 (초기 접힘) ──────────────────────────────┤
│ ▶ [로그 보기] 클릭 시 펼침                          │
└─────────────────────────────────────────────────────┘
```

- 상태 뱃지: SUCCESS=success, RUNNING=info, FAILED=danger, IDLE=neutral
- 로그는 기본 접힘, 요청 시에만 조회 (기존 정책 유지)

---

## 5. Number Format Implementation

### 5.1 `formatters.ts` 리팩토링 (새 API)

```ts
// 기본 포매터 (내부)
function formatNumber(value: number, opts?: { decimals?: number }): string
function formatKrMoney(value: number): string  // 만/억/조 자동 선택
function formatSign(value: number): '+' | '-' | ''
function formatArrow(value: number): '▲' | '▼' | '-' | ''

// Public API — 모든 호출부가 이들 중 하나만 사용
export function fmtPrice(value: number | null): string         // "72,500"
export function fmtPercent(value: number | null): string        // "2.46%"
export function fmtSignedPercent(value: number | null): string  // "+2.46%"
export function fmtCount(value: number | null): string          // "12,345"
export function fmtSignedCount(value: number | null): string    // "+1,234"
export function fmtKrMoney(value: number | null): string        // "32억", "1,240만"
export function fmtSignedKrMoney(value: number | null): string  // "+32억"
export function fmtEok(value: number | null, decimals?: 0|1|2): string  // "32.0억"
export function fmtSignedEok(value: number | null, decimals?: 0|1|2): string
export function fmtDate(value: string | null): string           // "2026-04-21"
export function fmtDateTime(value: string | null): string       // "04-21 14:30:12"
export function fmtTimeHm(value: string | null): string         // "14:30"

// Deprecated (제거 대상)
// - fmtSigned         (fmtSignedCount/SignedPrice로 분리)
// - fmtWon/fmtSignedWon (한국식 fmtKrMoney로 통합)
// - fmtWonToEok       (fmtEok으로 교체)
// - fmtCompactSigned  (영문 K/M/B 제거, fmtSignedKrMoney로 교체)
// - fmtNumber         (fmtCount로 교체)
```

### 5.2 치환 매트릭스 (기존 호출 → 신규)

| Before | After |
|--------|-------|
| `fmtNumber(x)` | `fmtCount(x)` |
| `fmtWon(x)` | `fmtPrice(x)` 또는 `fmtKrMoney(x)` (맥락별) |
| `fmtSignedWon(x)` | `fmtSignedKrMoney(x)` |
| `fmtWonToEok(x)` | `fmtEok(x)` |
| `fmtCompactSigned(x)` | `fmtSignedEok(x)` |
| `fmtSigned(x)` (가격용) | `fmtPrice(x)` |
| `value.toLocaleString('ko-KR')` | `fmtCount(x)` 또는 `fmtPrice(x)` |
| `value.toFixed(2)` | `fmtPercent(x)` |

### 5.3 `<Num />`와 formatters 결합

`<Num>`은 내부적으로 format prop에 따라 해당 포매터를 호출. 포매터는 순수 함수, `<Num>`은 렌더+스타일링 레이어.

```ts
// <Num> 내부
switch (format) {
  case 'price': return fmtPrice(value);
  case 'percent': return fmtPercent(value);
  case 'signed-percent': return fmtSignedPercent(value);
  case 'eok': return fmtEok(value);
  case 'signed-eok': return fmtSignedEok(value);
  case 'count': return fmtCount(value);
  case 'signed-count': return fmtSignedCount(value);
}
```

---

## 6. Data & State

### 6.1 상태 관리

- 기존 구조 유지 — Redux/Zustand 미도입
- `App.tsx`의 `useState` + prop drilling 유지
- 추가 상태:
  - Dashboard: `selectedPickTicker: string | null`
  - 종가배팅: `selectedItemTicker: string | null`, `drawerOpen: boolean`
  - 매매내역: `activeTab: 'positions' | 'daily' | 'executions'`

### 6.2 API/타입 변경

- **없음** — `types/api.ts` 그대로, 백엔드 변경 없음 (Plan §2.3 Out of Scope 준수)

---

## 7. Visual Regression Guard

### 7.1 기존 화면 기능 보존 체크리스트

각 화면 전환 전 수동 확인:

| 화면 | 보존 기능 |
|------|----------|
| Dashboard | 대시보드 새로고침 버튼, 추천 5종목 표시, 리포트 본문, 근거 링크 클릭 |
| 종가배팅 | Featured 5 구분, 전체 페이지네이션, 점수 분해, AI 분석, 뉴스 링크 |
| 누적 성과 | 등급별 성과, 거래 테이블, 비교값 갱신, 7일 롤링 안내, 페이지네이션 |
| 매매내역 | 계좌 KPI, 보유 종목, 일자별 손익, 체결 내역, 계좌 새로고침 |
| Data Status | 배치 상태, 상태 뱃지, 로그 조회 |

### 7.2 CSS 제거 체크

- [ ] `app.css`에서 `.closing-*`, `.dashboard-*`, `.metric-*` 등 기능별 클래스 제거
- [ ] 남은 app.css는 `body`, `html`, `:root`(토큰 re-export), 글로벌 reset 정도만 (≤50줄)
- [ ] 컴포넌트에서 class 참조가 모두 Tailwind 유틸 또는 프리미티브로 이관됨

---

## 8. Test Plan

### 8.1 L1 — 빌드/정적 검증

| ID | 시나리오 | Pass 조건 |
|----|----------|-----------|
| L1-01 | `npm run build` | exit 0, 에러 없음 |
| L1-02 | `tsc -b` 타입 체크 | 타입 에러 0건 |
| L1-03 | `grep -r "toLocaleString" frontend/src` | formatters.ts 외 0건 |
| L1-04 | `grep -r "fmtWon\|fmtCompactSigned" frontend/src` | 0건 (deprecated 함수 제거 확인) |
| L1-05 | `wc -l frontend/src/styles/app.css` | ≤50 |
| L1-06 | 프리미티브 9개 파일 존재 | 9/9 |

### 8.2 L2 — 시각/기능 검증 (수동)

| ID | 시나리오 | Pass 조건 |
|----|----------|-----------|
| L2-01 | 페이지 5개 순회 | 모두 정상 렌더, 콘솔 에러 0 |
| L2-02 | Dashboard 추천 후보 클릭 | 우측 상세 패널 업데이트 |
| L2-03 | 종가배팅 행 클릭 | Drawer 오픈, Escape 닫기 |
| L2-04 | 매매내역 탭 전환 | 탭 3개 모두 정상 렌더 |
| L2-05 | 외인/기관 음수 데이터 | `<Num tone="auto">`로 파란색 표시 |
| L2-06 | 수익률 0% | `+0.00%` 또는 `0.00%` (지정 규칙대로) |
| L2-07 | 가격 0원 | `0` 표시 (null만 `-`, B-03 검증) |
| L2-08 | 점수 바 너비 | `value / max * 100%` (B-02 검증) |
| L2-09 | 체결내역 15→11 컬럼 | 1440px에서 오버플로우 없음 또는 스크롤 가능 |
| L2-10 | 키보드 탭 | 버튼/링크/탭 키보드 접근 가능 |

### 8.3 L3 — E2E (옵션)

Playwright 미설치 상태 — L2의 수동 확인으로 대체. 필요 시 `/pdca qa` 단계에서 qa-lead가 도입 판단.

### 8.4 버그 오디트 검증 (17건 체크리스트)

Plan §6의 17개 버그 각각이 구조적으로 해결되었는지 Check 단계에서 확인.

---

## 9. Risks & Mitigations

Plan §8 리스크 계승 + Design 단계 신규:

| ID | 리스크 | 완화 |
|----|--------|------|
| R-07 | `<Num>` 도입이 너무 엄격해 일부 특수 포맷(점수 "18/22") 표현 불가 | `<Num>`은 선택적 사용, 인라인 JSX도 허용 (단 숫자 표시는 항상 경유) |
| R-08 | Drawer 자체 구현이 focus trap/스크롤 락 미흡 | v1은 최소 구현, 필요 시 `@radix-ui/react-dialog`로 교체 여지 (계약 유지) |
| R-09 | CSS 변수 fallback 없이 Tailwind 파싱 실패 | `tokens.css`는 `tailwind.css` 이전에 import, CI 빌드 확인 |
| R-10 | 기존 `clsx` 자체 구현과 npm `clsx` 충돌 | 자체 구현 유지 (가벼움) 또는 명시적 교체 |

---

## 10. Open Questions → 확정

Plan의 Open Questions에 대한 Design 단계 결정:

| Q | 결정 |
|---|------|
| Q1 (테이블 hover/selected 색상 분리) | **분리**: hover=`--bg-row-hover`, selected=`--bg-elevated` |
| Q2 (Dashboard 디테일 폭 비율) | **8:4** 고정 (1440px 기준 우측 최소 480px 확보) |
| Q3 (아이콘 라이브러리) | **lucide-react** 도입 (사이드바 메뉴 아이콘 + 탭/새로고침) |
| Q4 (등급 4단계 vs 전체) | **4단계 고정** (A/B/C/D), 그 외는 grade-d로 폴백 |
| Q5 (차트 도입) | **이번 사이클 미도입**, Out of Scope 유지. 필요 시 후속 feature |

---

## 11. Implementation Guide

### 11.1 구현 순서 (high-level)

Plan §10 기반, Design 단계에서 세션 분할 확정 (§11.3 참조).

### 11.2 Key Files to Create / Modify

**Create (19)**:
- `frontend/tailwind.config.ts`, `frontend/postcss.config.js`
- `frontend/src/styles/tokens.css`, `frontend/src/styles/tailwind.css`
- `frontend/src/components/ui/Num.tsx` ★
- `frontend/src/components/ui/Panel.tsx`
- `frontend/src/components/ui/Badge.tsx`
- `frontend/src/components/ui/DataTable.tsx` ★
- `frontend/src/components/ui/KpiStat.tsx`
- `frontend/src/components/ui/Tabs.tsx`
- `frontend/src/components/ui/OutcomePill.tsx`
- `frontend/src/components/ui/ScoreBar.tsx`
- `frontend/src/components/ui/Drawer.tsx`
- `frontend/src/components/dashboard/PicksTable.tsx`
- `frontend/src/components/dashboard/PickDetailPanel.tsx`
- `frontend/src/components/dashboard/MarketStrip.tsx`
- `frontend/src/components/closing/ClosingTable.tsx`
- `frontend/src/components/closing/ClosingDetailDrawer.tsx`
- `frontend/src/components/trade-history/PositionsTable.tsx`
- `frontend/src/components/trade-history/DailyPnlTable.tsx`
- `frontend/src/components/trade-history/ExecutionsTable.tsx`

**Modify (9)**:
- `frontend/package.json` (deps)
- `frontend/vite.config.ts` (if needed)
- `frontend/src/main.tsx` (import 순서: tokens → tailwind → app)
- `frontend/src/app/formatters.ts` (API 재정리)
- `frontend/src/components/layout/AppShell.tsx` (재작성)
- `frontend/src/components/dashboard/DashboardView.tsx` (재작성)
- `frontend/src/components/closing/ClosingView.tsx` (재작성)
- `frontend/src/components/performance/PerformanceView.tsx` (재작성)
- `frontend/src/components/trade-history/TradeHistoryView.tsx` (재작성)
- `frontend/src/components/batch/BatchStatusView.tsx` (재작성)
- `frontend/src/styles/app.css` (≤50줄 축소)

**Delete**: 없음 (기존 파일은 재작성 또는 유지)

### 11.3 Session Guide (Module Map)

**M1. Foundation** — Tailwind + 토큰 + 폰트 + 글로벌 리셋
- 파일: `tailwind.config.ts`, `postcss.config.js`, `src/styles/tokens.css`, `src/styles/tailwind.css`, `package.json`, `main.tsx`
- 의존 설치: `tailwindcss postcss autoprefixer clsx lucide-react`
- 폰트 self-host 또는 CDN (Pretendard, JetBrains Mono)
- Exit: `npm run build` 성공, dev 서버에서 기존 UI가 깨지지 않고 표시

**M2. Primitives — Num / Panel / Badge / ScoreBar / OutcomePill**
- 파일: `components/ui/Num.tsx`, `Panel.tsx`, `Badge.tsx`, `ScoreBar.tsx`, `OutcomePill.tsx`
- Exit: 스토리북 없이 빈 테스트 페이지에서 육안 확인 (또는 기존 페이지 몇 곳에 실험 적용)

**M3. Primitives — DataTable / KpiStat / Tabs / Drawer**
- 파일: `components/ui/DataTable.tsx`, `KpiStat.tsx`, `Tabs.tsx`, `Drawer.tsx`
- Exit: 9개 프리미티브 완성, import 체인 정리

**M4. Formatters Refactor + AppShell Rewrite**
- 파일: `src/app/formatters.ts`, `components/layout/AppShell.tsx`
- deprecated 함수 제거, grep 검증
- lucide-react 아이콘 사이드바 적용
- Exit: 앱이 기존 데이터로 로드되면서 쉘만 새 모습 (페이지 내부는 아직 기존)

**M5. Dashboard Rewrite**
- 파일: `DashboardView.tsx`, `PicksTable.tsx`, `PickDetailPanel.tsx`, `MarketStrip.tsx`
- 마스터/디테일 구조, 선택 상태 관리
- Exit: Dashboard 페이지 완전 신규 모습 + 기존 기능 모두 동작

**M6. Closing Bet Rewrite**
- 파일: `ClosingView.tsx`, `ClosingTable.tsx`, `ClosingDetailDrawer.tsx`
- 테이블 + 드로어, 점수 바 B-02 수정
- Exit: 종가배팅 페이지 신규 모습, Featured/전체 모두 테이블로 통합

**M7. Performance Rewrite**
- 파일: `PerformanceView.tsx`, `PerformanceTradeTable.tsx`, `GradeSummaryTable.tsx`
- KPI 스트립 + 등급 테이블 + 메인 테이블
- B-03 (formatPrice 0원) 수정
- Exit: 누적 성과 페이지 신규 모습

**M8. Trade History Rewrite**
- 파일: `TradeHistoryView.tsx`, `PositionsTable.tsx`, `DailyPnlTable.tsx`, `ExecutionsTable.tsx`
- 탭 구조, 컬럼 축소(B-06, B-07)
- Exit: 매매내역 페이지 신규 모습, 탭 동작 확인

**M9. Data Status + Batch Rewrite**
- 파일: `BatchStatusView.tsx`, `BatchLogPanel.tsx`
- 배치 그리드 + 로그 접힘 패널
- Exit: Data Status 페이지 신규 모습

**M10. Global CSS Cleanup + Bug Sweep + Build Verify**
- `app.css` ≤50줄로 축소
- Plan §6 버그 오디트 17건 체크리스트 전수 확인
- `npm run build` 최종 통과
- 1440×900에서 5페이지 모두 스크린샷 확인
- Exit: Plan Success Criteria 10개 모두 ✅ 근접

### 11.4 Recommended Session Plan

사용자는 Plan 단계에서 **"한 번에 전체 재개편"**을 선택했으나, **구현 품질 확보**를 위해 논리적으로 세션을 다음과 같이 묶기를 권장:

| 세션 | 포함 모듈 | 검증 지점 |
|------|----------|-----------|
| Session 1 | M1 + M2 + M3 | 프리미티브 완성, 빌드 통과 |
| Session 2 | M4 + M5 | AppShell + Dashboard 완성 (신규 스타일 첫 체감) |
| Session 3 | M6 + M7 | 종가배팅 + 누적 성과 완성 |
| Session 4 | M8 + M9 + M10 | 매매내역 + Data Status + 최종 정돈 |

실행 명령:

```bash
/pdca do ui-modern-overhaul --scope M1,M2,M3
/pdca do ui-modern-overhaul --scope M4,M5
/pdca do ui-modern-overhaul --scope M6,M7
/pdca do ui-modern-overhaul --scope M8,M9,M10
```

또는 단일 세션:

```bash
/pdca do ui-modern-overhaul
```

---

## 12. Design Decisions Recap (Decision Record)

| ID | 결정 | 근거 |
|----|------|------|
| D-01 | Option C (Pragmatic Primitives) | 1인 트레이딩 앱 규모에 균형, 버그 B-01 구조적 해결 |
| D-02 | 한국식 등락 색상 (빨강↑ 파랑↓) | 사용자 확정 (Plan Checkpoint 2) |
| D-03 | `<Num>` 단일 숫자 컴포넌트 | 포맷·색상·폰트 일관성 단일 진입점 |
| D-04 | CSS Variables + Tailwind | 토큰 재정의 용이, 향후 라이트테마 확장 여지 |
| D-05 | 외부 UI 라이브러리 미도입 (lucide 제외) | 번들 크기 최소, 프로젝트 정체성 유지 |
| D-06 | Drawer 자체 구현 v1, 필요 시 Radix 교체 | 초기 단순화, 접근성 부족 시 교체 계약 유지 |
| D-07 | 차트 미도입 | Out of Scope, 후속 feature로 분리 |
| D-08 | 4단계 등급 고정 | 나머지는 grade-d 폴백 |

---

## 13. Next Phase

- **Do**: `/pdca do ui-modern-overhaul` (전체) 또는 `/pdca do ui-modern-overhaul --scope M1,M2,M3` (권장 분할)
- 이후: `/pdca analyze` → (`/pdca iterate` if <90%) → `/pdca qa` → `/pdca report`

---

*Design generated 2026-04-21 via `/pdca design ui-modern-overhaul`. Architecture: Option C (Pragmatic Primitives).*

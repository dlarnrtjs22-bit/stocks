// Design Ref: Design §5 — 숫자 포맷 단일 진입점.
// Plan SC-03: 모든 숫자 출력은 이 파일을 경유. toLocaleString 직접 호출 금지.
// 기존 함수는 하위 호환을 위해 유지 (M5-M9에서 점진 치환, M10에서 제거).

// ───────────────────────────────────────────────────────────
// Internal helpers
// ───────────────────────────────────────────────────────────
function toNum(value: number | null | undefined): number {
  if (value === null || value === undefined) return 0;
  if (typeof value !== 'number' || Number.isNaN(value)) return 0;
  return value;
}

function formatNumber(value: number, decimals = 0): string {
  return new Intl.NumberFormat('ko-KR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

// ───────────────────────────────────────────────────────────
// Public API (new) — use these in new code
// ───────────────────────────────────────────────────────────

/** 가격/수량 단위 생략 숫자: 72,500 */
export function fmtPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return formatNumber(toNum(value));
}

/** 건수/종목수 등 카운트: 12,345 */
export function fmtCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return formatNumber(toNum(value));
}

/** 부호 포함 카운트: +1,234 / -1,234 / 0 */
export function fmtSignedCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  const n = toNum(value);
  if (n > 0) return `+${formatNumber(n)}`;
  return formatNumber(n);
}

/** 퍼센트 (부호 없음, 소수점 2자리): 2.46% */
export function fmtPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return `${toNum(value).toFixed(2)}%`;
}

/** 부호 포함 퍼센트 (소수점 2자리): +2.46% / -1.23% / 0.00% */
export function fmtSignedPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  const n = toNum(value);
  if (n > 0) return `+${n.toFixed(2)}%`;
  return `${n.toFixed(2)}%`;
}

/** 억 단위 고정: 32.0억. decimals 기본 1. */
export function fmtEok(value: number | null | undefined, decimals: 0 | 1 | 2 = 1): string {
  if (value === null || value === undefined) return '-';
  const eok = toNum(value) / 100_000_000;
  return `${formatNumber(eok, decimals)}억`;
}

/** 부호 포함 억 단위: +32.0억 / -4.5억 / 0.0억 */
export function fmtSignedEok(value: number | null | undefined, decimals: 0 | 1 | 2 = 1): string {
  if (value === null || value === undefined) return '-';
  const eok = toNum(value) / 100_000_000;
  const body = `${formatNumber(Math.abs(eok), decimals)}억`;
  if (eok > 0) return `+${body}`;
  if (eok < 0) return `-${body}`;
  return `${formatNumber(0, decimals)}억`;
}

/** 한국식 금액 자동 단위: ≥1억=X.X억, ≥1천만=X,XXX만, else=X,XXX원 */
export function fmtKrMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  const n = toNum(value);
  const abs = Math.abs(n);
  if (abs >= 100_000_000) return fmtEok(n, 1);
  if (abs >= 10_000_000) return `${formatNumber(n / 10_000, 0)}만`;
  if (abs >= 10_000) return `${formatNumber(n / 10_000, 1)}만`;
  return `${formatNumber(n, 0)}원`;
}

/** 부호 포함 한국식 금액 */
export function fmtSignedKrMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  const n = toNum(value);
  const body = fmtKrMoney(Math.abs(n));
  if (n > 0) return `+${body}`;
  if (n < 0) return `-${body}`;
  return body;
}

// ───────────────────────────────────────────────────────────
// Date / Time helpers (new names)
// ───────────────────────────────────────────────────────────

export function fmtDate(value?: string | null): string {
  if (!value) return '-';
  const raw = String(value);
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${match[1]}-${match[2]}-${match[3]}`;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

export function fmtDateTime(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date);
}

export function fmtTimeHm(value?: string | null): string {
  if (!value) return '-';
  const raw = String(value);
  const match = raw.match(/T(\d{2}):(\d{2})/);
  if (match) return `${match[1]}:${match[2]}`;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return raw;
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

// Legacy API removed in M10. 마이그레이션 경로:
//   fmtNumber         → fmtCount
//   fmtWon            → fmtKrMoney 또는 `${fmtPrice(v)}원`
//   fmtSignedWon      → fmtSignedKrMoney
//   fmtWonToEok       → fmtEok
//   fmtCompactSigned  → fmtSignedEok 또는 fmtSignedKrMoney
//   fmtSigned         → fmtSignedCount 또는 fmtPrice
//   clsx (local)      → npm 'clsx' 패키지 직접 import

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
  if (match) {
    return `${match[1]}:${match[2]}`;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}

export function fmtNumber(value: number): string {
  return new Intl.NumberFormat('ko-KR').format(Number(value || 0));
}

function trimCompact(value: number): string {
  return value
    .toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2)
    .replace(/\.0+$/, '')
    .replace(/(\.\d*[1-9])0+$/, '$1');
}

export function fmtWonToEok(value: number): string {
  const eok = Number(value || 0) / 100000000;
  return `${fmtNumber(Math.round(eok))}억`;
}

export function fmtWon(value: number): string {
  return `${fmtNumber(Number(value || 0))}원`;
}

export function fmtSignedWon(value: number): string {
  const number = Number(value || 0);
  if (number > 0) return `+${fmtNumber(number)}원`;
  if (number < 0) return `-${fmtNumber(Math.abs(number))}원`;
  return '0원';
}

export function fmtSigned(value: number): string {
  const number = Number(value || 0);
  if (number > 0) return `+${number.toLocaleString('ko-KR')}`;
  return number.toLocaleString('ko-KR');
}

export function fmtSignedPercent(value: number): string {
  const number = Number(value || 0);
  if (number > 0) return `+${number.toFixed(2)}%`;
  return `${number.toFixed(2)}%`;
}

export function fmtCompactSigned(value: number): string {
  const number = Number(value || 0);
  const abs = Math.abs(number);
  let body = '';

  if (abs >= 1_000_000_000) {
    body = `${trimCompact(abs / 1_000_000_000)}B`;
  } else if (abs >= 1_000_000) {
    body = `${trimCompact(abs / 1_000_000)}M`;
  } else if (abs >= 1_000) {
    body = `${trimCompact(abs / 1_000)}K`;
  } else {
    body = fmtNumber(abs);
  }

  if (number > 0) return `+${body}`;
  if (number < 0) return `-${body}`;
  return body;
}

export function clsx(...items: Array<string | false | null | undefined>): string {
  return items.filter(Boolean).join(' ');
}

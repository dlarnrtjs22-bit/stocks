import React from 'react';
import clsx from 'clsx';
import {
  fmtPrice,
  fmtCount,
  fmtPercent,
  fmtSignedPercent,
  fmtEok,
  fmtSignedEok,
  fmtSignedCount,
  fmtSignedKrMoney,
  fmtKrMoney,
} from '../../app/formatters';

// Design Ref: Design §3.1 — 모든 숫자 출력의 단일 진입점.
// Plan §6 버그 B-01/B-03/B-11/B-13-14/B-17를 구조적으로 차단한다.

export type NumFormat =
  | 'price'
  | 'percent'
  | 'signed-percent'
  | 'count'
  | 'signed-count'
  | 'eok'
  | 'signed-eok'
  | 'kr-money'
  | 'signed-kr-money';

interface NumProps {
  value: number | null | undefined;
  format: NumFormat;
  tone?: 'auto' | 'neutral' | 'muted';
  decimals?: 0 | 1 | 2;
  showArrow?: boolean;
  className?: string;
}

function resolveColor(value: number, tone: NumProps['tone']): string {
  if (tone === 'muted') return 'text-text-muted';
  if (tone === 'neutral') return 'text-text-primary';
  if (value > 0) return 'text-up';
  if (value < 0) return 'text-down';
  return 'text-text-primary';
}

function formatValue(value: number, format: NumFormat, decimals?: 0 | 1 | 2): string {
  switch (format) {
    case 'price':
      return fmtPrice(value);
    case 'percent':
      return fmtPercent(value);
    case 'signed-percent':
      return fmtSignedPercent(value);
    case 'count':
      return fmtCount(value);
    case 'signed-count':
      return fmtSignedCount(value);
    case 'eok':
      return fmtEok(value, decimals);
    case 'signed-eok':
      return fmtSignedEok(value, decimals);
    case 'kr-money':
      return fmtKrMoney(value);
    case 'signed-kr-money':
      return fmtSignedKrMoney(value);
    default:
      return String(value);
  }
}

const SIGNED_FORMATS: NumFormat[] = ['signed-percent', 'signed-count', 'signed-eok', 'signed-kr-money'];

export function Num({
  value,
  format,
  tone,
  decimals,
  showArrow,
  className,
}: NumProps) {
  if (value === null || value === undefined || (typeof value === 'number' && Number.isNaN(value))) {
    return <span className={clsx('num text-text-muted', className)}>-</span>;
  }

  const isSigned = SIGNED_FORMATS.includes(format);
  const effectiveTone: NumProps['tone'] = tone ?? (isSigned ? 'auto' : 'neutral');
  const color = resolveColor(value, effectiveTone);
  const formatted = formatValue(value, format, decimals);

  const arrow = showArrow
    ? value > 0
      ? '▲'
      : value < 0
        ? '▼'
        : ''
    : '';

  return (
    <span className={clsx('num', color, className)}>
      {arrow ? <span className="mr-0.5 text-xs">{arrow}</span> : null}
      {formatted}
    </span>
  );
}

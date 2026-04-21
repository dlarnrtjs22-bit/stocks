import React from 'react';
import clsx from 'clsx';

// Design Ref: Design §3.5 — 상단 KPI 통계 블록.

interface KpiStatProps {
  label: React.ReactNode;
  value: React.ReactNode;
  delta?: React.ReactNode;
  hint?: React.ReactNode;
  tone?: 'default' | 'up' | 'down';
  className?: string;
}

const toneClasses: Record<NonNullable<KpiStatProps['tone']>, string> = {
  default: 'text-text-primary',
  up: 'text-up',
  down: 'text-down',
};

export function KpiStat({
  label,
  value,
  delta,
  hint,
  tone = 'default',
  className,
}: KpiStatProps) {
  return (
    <div
      className={clsx(
        'flex flex-col gap-1 rounded-md border border-border-subtle bg-surface px-3 py-2.5',
        className,
      )}
    >
      <div className="text-xs text-text-secondary uppercase tracking-wide">{label}</div>
      <div className={clsx('text-xl font-semibold leading-none', toneClasses[tone])}>
        {value}
      </div>
      {delta ? <div className="text-xs text-text-secondary">{delta}</div> : null}
      {hint ? <div className="text-xs text-text-muted">{hint}</div> : null}
    </div>
  );
}

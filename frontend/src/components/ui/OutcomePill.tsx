import React from 'react';
import clsx from 'clsx';

// Design Ref: Design §3.7 — WIN/LOSS/OPEN 결과 표시.
// 한국식: WIN=빨강(up), LOSS=파랑(down), OPEN=회색(flat), PENDING=warn.

export type Outcome = 'WIN' | 'LOSS' | 'OPEN' | 'PENDING' | string;

interface OutcomePillProps {
  outcome: Outcome;
  size?: 'xs' | 'sm';
  className?: string;
}

const outcomeMap: Record<
  string,
  { label: string; classes: string }
> = {
  WIN: {
    label: 'Win',
    classes: 'bg-up-bg text-up border-up/30',
  },
  LOSS: {
    label: 'Loss',
    classes: 'bg-down-bg text-down border-down/30',
  },
  OPEN: {
    label: 'Open',
    classes: 'bg-elevated text-text-secondary border-border-subtle',
  },
  PENDING: {
    label: 'Pending',
    classes: 'bg-warn/15 text-warn border-warn/30',
  },
};

const sizeClasses: Record<NonNullable<OutcomePillProps['size']>, string> = {
  xs: 'text-[10px] px-1.5 py-0.5',
  sm: 'text-xs px-2 py-0.5',
};

export function OutcomePill({
  outcome,
  size = 'xs',
  className,
}: OutcomePillProps) {
  const key = String(outcome || '').toUpperCase();
  const entry = outcomeMap[key] ?? {
    label: outcome,
    classes: 'bg-elevated text-text-secondary border-border-subtle',
  };
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-sm border font-medium whitespace-nowrap',
        entry.classes,
        sizeClasses[size],
        className,
      )}
    >
      {entry.label}
    </span>
  );
}

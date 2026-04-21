import React from 'react';
import clsx from 'clsx';

// Design Ref: Design §3.8 — 점수 바. Plan 버그 B-02 해결 (매직 넘버 34 제거, max 정규화).

interface ScoreBarProps {
  value: number;
  max: number;
  label?: React.ReactNode;
  compact?: boolean;
  className?: string;
}

export function ScoreBar({
  value,
  max,
  label,
  compact = false,
  className,
}: ScoreBarProps) {
  const safeMax = max <= 0 ? 1 : max;
  const ratio = Math.max(0, Math.min(1, value / safeMax));
  const pct = ratio * 100;

  const color =
    ratio >= 0.75
      ? 'bg-up'
      : ratio >= 0.5
        ? 'bg-brand'
        : ratio >= 0.25
          ? 'bg-warn'
          : 'bg-flat';

  return (
    <div className={clsx('flex items-center gap-2', className)}>
      {label ? (
        <span className="text-xs text-text-secondary whitespace-nowrap shrink-0">{label}</span>
      ) : null}
      <div
        className={clsx(
          'relative flex-1 overflow-hidden rounded-sm bg-border-subtle',
          compact ? 'h-1' : 'h-1.5',
        )}
      >
        <div
          className={clsx('h-full transition-all', color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="num text-xs text-text-primary whitespace-nowrap shrink-0">
        {value}
        <span className="text-text-muted">/{max}</span>
      </span>
    </div>
  );
}

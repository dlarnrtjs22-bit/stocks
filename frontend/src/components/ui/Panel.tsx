import React from 'react';
import clsx from 'clsx';

// Design Ref: Design §3.2 — 카드/섹션 컨테이너.

interface PanelProps {
  tone?: 'default' | 'subtle' | 'elevated';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  bordered?: boolean;
  className?: string;
  children: React.ReactNode;
}

const toneClasses: Record<NonNullable<PanelProps['tone']>, string> = {
  default: 'bg-surface',
  subtle: 'bg-base',
  elevated: 'bg-elevated shadow-elevated',
};

const paddingClasses: Record<NonNullable<PanelProps['padding']>, string> = {
  none: 'p-0',
  sm: 'p-2',
  md: 'p-3',
  lg: 'p-4',
};

export function Panel({
  tone = 'default',
  padding = 'md',
  title,
  subtitle,
  action,
  bordered = true,
  className,
  children,
}: PanelProps) {
  return (
    <section
      className={clsx(
        'rounded-md',
        toneClasses[tone],
        bordered && tone !== 'elevated' && 'border border-border-subtle',
        className,
      )}
    >
      {(title || action) && (
        <header
          className={clsx(
            'flex items-center justify-between gap-3 border-b border-border-subtle',
            padding === 'none' ? 'px-3 py-2' : 'px-3 py-2',
          )}
        >
          <div className="min-w-0">
            {title && (
              <h3 className="text-md font-semibold text-text-primary truncate">{title}</h3>
            )}
            {subtitle && (
              <div className="text-xs text-text-muted mt-0.5 truncate">{subtitle}</div>
            )}
          </div>
          {action && <div className="shrink-0 flex items-center gap-2">{action}</div>}
        </header>
      )}
      <div className={clsx(paddingClasses[padding])}>{children}</div>
    </section>
  );
}

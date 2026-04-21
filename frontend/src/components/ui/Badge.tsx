import React from 'react';
import clsx from 'clsx';

// Design Ref: Design §3.3 — 등급/상태 태그.

export type BadgeVariant =
  | 'grade-a'
  | 'grade-b'
  | 'grade-c'
  | 'grade-d'
  | 'success'
  | 'warn'
  | 'danger'
  | 'info'
  | 'up'
  | 'down'
  | 'flat'
  | 'neutral';

interface BadgeProps {
  variant?: BadgeVariant;
  size?: 'xs' | 'sm';
  className?: string;
  children: React.ReactNode;
}

const variantClasses: Record<BadgeVariant, string> = {
  'grade-a': 'bg-grade-a/15 text-grade-a border-grade-a/30',
  'grade-b': 'bg-grade-b/15 text-grade-b border-grade-b/30',
  'grade-c': 'bg-grade-c/15 text-grade-c border-grade-c/30',
  'grade-d': 'bg-grade-d/15 text-grade-d border-grade-d/30',
  success: 'bg-success/15 text-success border-success/30',
  warn: 'bg-warn/15 text-warn border-warn/30',
  danger: 'bg-danger/15 text-danger border-danger/30',
  info: 'bg-info/15 text-info border-info/30',
  up: 'bg-up-bg text-up border-up/30',
  down: 'bg-down-bg text-down border-down/30',
  flat: 'bg-flat/15 text-flat border-flat/30',
  neutral: 'bg-elevated text-text-secondary border-border-subtle',
};

const sizeClasses: Record<NonNullable<BadgeProps['size']>, string> = {
  xs: 'text-[10px] leading-none px-1.5 py-0.5 rounded-sm',
  sm: 'text-xs leading-none px-2 py-0.5 rounded-sm',
};

export function Badge({
  variant = 'neutral',
  size = 'sm',
  className,
  children,
}: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center border font-medium whitespace-nowrap',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function gradeVariant(grade: string | null | undefined): BadgeVariant {
  const g = (grade || '').toUpperCase();
  if (g === 'A' || g === 'S') return 'grade-a';
  if (g === 'B') return 'grade-b';
  if (g === 'C') return 'grade-c';
  return 'grade-d';
}

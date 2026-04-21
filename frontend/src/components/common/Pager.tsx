import React from 'react';
import clsx from 'clsx';
import { ChevronLeft, ChevronRight } from 'lucide-react';

// Design Ref: Design §11.2 — 페이지네이션.
interface PagerProps {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}

export function Pager({ page, totalPages, onChange }: PagerProps) {
  if (!totalPages || totalPages <= 1) return null;

  const buttonCls = clsx(
    'inline-flex items-center gap-1 px-2.5 py-1 rounded-md border text-xs font-medium transition-colors',
    'border-border bg-surface text-text-primary hover:bg-elevated',
    'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-surface',
  );

  return (
    <div className="flex items-center justify-center gap-2">
      <button
        type="button"
        className={buttonCls}
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        <ChevronLeft size={12} />
        이전
      </button>
      <span className="num text-sm text-text-secondary min-w-[56px] text-center">
        {page} / {totalPages}
      </span>
      <button
        type="button"
        className={buttonCls}
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
      >
        다음
        <ChevronRight size={12} />
      </button>
    </div>
  );
}

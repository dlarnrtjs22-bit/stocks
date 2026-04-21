import React, { useEffect } from 'react';
import clsx from 'clsx';
import { X } from 'lucide-react';

// Design Ref: Design §3.9 — 우측 슬라이드 상세 패널 (자체 구현 v1).

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  width?: 'md' | 'lg' | 'xl';
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  footer?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}

const widthClasses: Record<NonNullable<DrawerProps['width']>, string> = {
  md: 'w-[420px]',
  lg: 'w-[560px]',
  xl: 'w-[720px]',
};

export function Drawer({
  open,
  onClose,
  width = 'lg',
  title,
  subtitle,
  footer,
  children,
  className,
}: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  return (
    <div
      aria-hidden={!open}
      className={clsx(
        'fixed inset-0 z-50 transition-opacity',
        open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0',
      )}
    >
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        className={clsx(
          'absolute right-0 top-0 h-full max-w-full bg-surface border-l border-border shadow-elevated',
          'flex flex-col transition-transform duration-200',
          widthClasses[width],
          open ? 'translate-x-0' : 'translate-x-full',
          className,
        )}
      >
        <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border-subtle shrink-0">
          <div className="min-w-0">
            {title && (
              <h3 className="text-md font-semibold text-text-primary truncate">{title}</h3>
            )}
            {subtitle && (
              <div className="text-xs text-text-muted truncate mt-0.5">{subtitle}</div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="shrink-0 p-1 rounded hover:bg-elevated text-text-secondary hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
        {footer ? (
          <footer className="shrink-0 border-t border-border-subtle px-4 py-3">
            {footer}
          </footer>
        ) : null}
      </aside>
    </div>
  );
}

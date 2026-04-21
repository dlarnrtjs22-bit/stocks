import React from 'react';
import clsx from 'clsx';

// Design Ref: Design §3.6 — 탭 컨테이너. 외부 라이브러리 없이 자체 구현.

interface TabItem {
  value: string;
  label: React.ReactNode;
  count?: number;
}

interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  items: TabItem[];
  variant?: 'segmented' | 'underline';
  className?: string;
}

export function Tabs({
  value,
  onChange,
  items,
  variant = 'underline',
  className,
}: TabsProps) {
  const handleKey = (event: React.KeyboardEvent, currentIndex: number) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      const prev = (currentIndex - 1 + items.length) % items.length;
      onChange(items[prev].value);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      const next = (currentIndex + 1) % items.length;
      onChange(items[next].value);
    }
  };

  if (variant === 'segmented') {
    return (
      <div
        role="tablist"
        className={clsx(
          'inline-flex items-center gap-0.5 rounded-md border border-border-subtle bg-base p-0.5',
          className,
        )}
      >
        {items.map((item, index) => {
          const active = item.value === value;
          return (
            <button
              key={item.value}
              role="tab"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(item.value)}
              onKeyDown={(e) => handleKey(e, index)}
              className={clsx(
                'px-3 py-1 rounded-sm text-sm transition-colors',
                active
                  ? 'bg-elevated text-text-primary font-medium'
                  : 'text-text-secondary hover:text-text-primary',
              )}
            >
              {item.label}
              {typeof item.count === 'number' ? (
                <span className="ml-1.5 text-xs text-text-muted">{item.count}</span>
              ) : null}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      role="tablist"
      className={clsx('flex items-center gap-1 border-b border-border-subtle', className)}
    >
      {items.map((item, index) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={(e) => handleKey(e, index)}
            className={clsx(
              'relative px-3 py-2 text-sm transition-colors',
              active
                ? 'text-text-primary font-medium'
                : 'text-text-secondary hover:text-text-primary',
            )}
          >
            <span>{item.label}</span>
            {typeof item.count === 'number' ? (
              <span className="ml-1.5 text-xs text-text-muted">{item.count}</span>
            ) : null}
            {active ? (
              <span className="absolute inset-x-0 -bottom-px h-0.5 bg-brand" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

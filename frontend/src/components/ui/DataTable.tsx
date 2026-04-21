import React from 'react';
import clsx from 'clsx';

// Design Ref: Design §3.4 — Trading Pro 테이블 래퍼.
// sticky header, 행 hover/selected, 수평 스크롤, 컬럼 정렬 지원.

export interface Column<T> {
  key: string;
  header: React.ReactNode;
  width?: string;
  align?: 'left' | 'right' | 'center';
  headerAlign?: 'left' | 'right' | 'center';
  render: (row: T, index: number) => React.ReactNode;
  className?: string;
  headerClassName?: string;
}

interface DataTableProps<T> {
  columns: Array<Column<T>>;
  data: T[];
  rowKey: (row: T, index: number) => string | number;
  onRowClick?: (row: T, index: number) => void;
  selectedKey?: string | number | null;
  emptyMessage?: React.ReactNode;
  dense?: boolean;
  stickyHeader?: boolean;
  className?: string;
  minWidth?: string;
}

function alignClass(align?: 'left' | 'right' | 'center'): string {
  if (align === 'right') return 'text-right';
  if (align === 'center') return 'text-center';
  return 'text-left';
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  onRowClick,
  selectedKey,
  emptyMessage = '데이터 없음',
  dense = false,
  stickyHeader = true,
  className,
  minWidth,
}: DataTableProps<T>) {
  const rowPadding = dense ? 'px-2 py-1' : 'px-2.5 py-1.5';
  const headerPadding = dense ? 'px-2 py-1.5' : 'px-2.5 py-2';

  return (
    <div className={clsx('w-full overflow-x-auto', className)}>
      <table
        className="w-full border-collapse text-sm"
        style={minWidth ? { minWidth } : undefined}
      >
        <colgroup>
          {columns.map((col) => (
            <col key={col.key} style={col.width ? { width: col.width } : undefined} />
          ))}
        </colgroup>
        <thead
          className={clsx(
            'bg-surface border-b border-border',
            stickyHeader && 'sticky top-0 z-10',
          )}
        >
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={clsx(
                  headerPadding,
                  'text-xs font-medium text-text-secondary uppercase tracking-wide',
                  alignClass(col.headerAlign ?? col.align),
                  col.headerClassName,
                )}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="text-center text-text-muted py-6"
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, index) => {
              const key = rowKey(row, index);
              const isSelected = selectedKey != null && key === selectedKey;
              const clickable = typeof onRowClick === 'function';
              return (
                <tr
                  key={key}
                  className={clsx(
                    'border-b border-border-subtle transition-colors',
                    clickable && 'cursor-pointer',
                    isSelected
                      ? 'bg-elevated'
                      : clickable
                        ? 'hover:bg-row-hover'
                        : '',
                  )}
                  onClick={clickable ? () => onRowClick?.(row, index) : undefined}
                >
                  {columns.map((col) => (
                    <td
                      key={col.key}
                      className={clsx(
                        rowPadding,
                        'text-text-primary align-middle',
                        alignClass(col.align),
                        col.className,
                      )}
                    >
                      {col.render(row, index)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

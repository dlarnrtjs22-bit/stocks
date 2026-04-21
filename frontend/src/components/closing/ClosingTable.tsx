import React from 'react';
import { Star } from 'lucide-react';
import clsx from 'clsx';
import type { ClosingBetItem } from '../../types/api';
import { DataTable, type Column } from '../ui/DataTable';
import { Num } from '../ui/Num';
import { Badge, gradeVariant } from '../ui/Badge';

// Design Ref: Design §4.3 — 종가배팅 메인 테이블 (Featured 5는 ★로 통합).

export interface ClosingTableRow extends ClosingBetItem {
  isFeatured: boolean;
  displayRank: number;
}

interface ClosingTableProps {
  rows: ClosingTableRow[];
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
}

export function ClosingTable({ rows, selectedTicker, onSelect }: ClosingTableProps) {
  const columns: Column<ClosingTableRow>[] = [
    {
      key: 'featured',
      header: '',
      width: '32px',
      align: 'center',
      render: (row) =>
        row.isFeatured ? (
          <Star size={12} className="text-warn fill-warn inline-block" />
        ) : (
          <span className="text-text-muted text-xs">·</span>
        ),
    },
    {
      key: 'rank',
      header: '#',
      width: '40px',
      align: 'right',
      render: (row) => (
        <span className="num text-xs text-text-muted">{row.displayRank}</span>
      ),
    },
    {
      key: 'grade',
      header: '등급',
      width: '64px',
      render: (row) => (
        <div className="flex flex-col gap-0.5">
          <Badge variant={gradeVariant(row.grade)}>{row.grade}</Badge>
          {row.base_grade && row.base_grade !== row.grade ? (
            <span className="text-[10px] text-text-muted">원{row.base_grade}</span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'name',
      header: '종목',
      render: (row) => (
        <div className="min-w-0">
          <div className="text-sm text-text-primary font-medium truncate">{row.name}</div>
          <div className="num text-xs text-text-muted">
            {row.ticker} <span className="ml-1">{row.market}</span>
          </div>
        </div>
      ),
    },
    {
      key: 'score',
      header: '점수',
      width: '64px',
      align: 'right',
      render: (row) => (
        <span className="num text-text-primary">
          {row.score_total}
          <span className="text-text-muted">/{row.score_max}</span>
        </span>
      ),
    },
    {
      key: 'price',
      header: '현재가',
      width: '100px',
      align: 'right',
      render: (row) => <Num value={row.current_price} format="price" />,
    },
    {
      key: 'change',
      header: '변동',
      width: '90px',
      align: 'right',
      render: (row) => <Num value={row.change_pct} format="signed-percent" showArrow />,
    },
    {
      key: 'value',
      header: '거래대금',
      width: '90px',
      align: 'right',
      render: (row) => <Num value={row.trading_value} format="eok" tone="neutral" />,
    },
    {
      key: 'decision',
      header: '결정',
      width: '100px',
      render: (row) => (
        <Badge
          variant={
            row.ai_opinion === '매수' || row.decision_status === 'BUY' ? 'up' : 'neutral'
          }
          size="xs"
        >
          {row.decision_label || row.decision_status || '-'}
        </Badge>
      ),
    },
    {
      key: 'themes',
      header: '테마',
      render: (row) => (
        <div className="flex flex-wrap gap-1 max-w-[160px]">
          {row.themes.slice(0, 3).map((theme, i) => (
            <span
              key={`${row.ticker}-th-${i}`}
              className="inline-flex items-center px-1.5 py-px rounded-sm border border-border-subtle bg-base text-[10px] text-text-secondary whitespace-nowrap"
            >
              {theme}
            </span>
          ))}
          {row.themes.length > 3 ? (
            <span className="text-[10px] text-text-muted">+{row.themes.length - 3}</span>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={rows}
      rowKey={(row) => row.ticker}
      selectedKey={selectedTicker}
      onRowClick={(row) => onSelect(row.ticker)}
      emptyMessage={<span className={clsx('text-text-muted')}>종가배팅 후보 없음</span>}
      dense
    />
  );
}

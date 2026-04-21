import React from 'react';
import type { DashboardPickPayload } from '../../types/api';
import { DataTable, type Column } from '../ui/DataTable';
import { Num } from '../ui/Num';
import { Badge, gradeVariant } from '../ui/Badge';

// Design Ref: Design §4.2 — 추천 후보 테이블 (마스터).

interface PicksTableProps {
  picks: DashboardPickPayload[];
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
}

export function PicksTable({ picks, selectedTicker, onSelect }: PicksTableProps) {
  const columns: Column<DashboardPickPayload>[] = [
    {
      key: 'grade',
      header: '등급',
      width: '60px',
      render: (pick) => <Badge variant={gradeVariant(pick.grade)}>{pick.grade}</Badge>,
    },
    {
      key: 'name',
      header: '종목',
      render: (pick) => (
        <div className="min-w-0">
          <div className="text-sm text-text-primary font-medium truncate">{pick.name}</div>
          <div className="num text-xs text-text-muted">{pick.ticker}</div>
        </div>
      ),
    },
    {
      key: 'market',
      header: '시장',
      width: '80px',
      render: (pick) => (
        <span className="text-xs text-text-secondary">{pick.market}</span>
      ),
    },
    {
      key: 'price',
      header: '현재가',
      width: '100px',
      align: 'right',
      render: (pick) => <Num value={pick.current_price} format="price" />,
    },
    {
      key: 'change',
      header: '변동',
      width: '90px',
      align: 'right',
      render: (pick) => <Num value={pick.change_pct} format="signed-percent" showArrow />,
    },
    {
      key: 'score',
      header: '점수',
      width: '60px',
      align: 'right',
      render: (pick) => (
        <span className="num text-text-primary">
          {pick.score_total}
          <span className="text-text-muted">/22</span>
        </span>
      ),
    },
    {
      key: 'value',
      header: '거래대금',
      width: '90px',
      align: 'right',
      render: (pick) => <Num value={pick.trading_value} format="eok" tone="neutral" />,
    },
    {
      key: 'decision',
      header: '결정',
      width: '90px',
      render: (pick) => (
        <Badge
          variant={pick.decision_status === 'BUY' ? 'up' : 'neutral'}
          size="xs"
        >
          {pick.decision_label || pick.decision_status || '-'}
        </Badge>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={picks}
      rowKey={(pick) => pick.ticker}
      selectedKey={selectedTicker}
      onRowClick={(pick) => onSelect(pick.ticker)}
      emptyMessage="추천 후보 없음"
      dense
    />
  );
}

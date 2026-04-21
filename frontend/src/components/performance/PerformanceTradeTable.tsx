import React from 'react';
import type { PerformanceTradeItem } from '../../types/api';
import { DataTable, type Column } from '../ui/DataTable';
import { Num } from '../ui/Num';
import { Badge, gradeVariant } from '../ui/Badge';
import { OutcomePill } from '../ui/OutcomePill';
import { fmtTimeHm } from '../../app/formatters';

// Design Ref: Design §4.4 — 누적 성과 거래 테이블.
// Plan 버그 B-03 해결: 가격 0원이 '-'로 표시되던 falsy 버그를 <Num>이 구조적으로 차단.
// Plan 버그 B-11 해결: toLocaleString 직접 호출 제거.

interface PerformanceTradeTableProps {
  trades: PerformanceTradeItem[];
}

export function PerformanceTradeTable({ trades }: PerformanceTradeTableProps) {
  const columns: Column<PerformanceTradeItem>[] = [
    {
      key: 'grade',
      header: '등급',
      width: '60px',
      render: (trade) => <Badge variant={gradeVariant(trade.grade)}>{trade.grade}</Badge>,
    },
    {
      key: 'name',
      header: '종목',
      render: (trade) => (
        <div className="min-w-0">
          <div className="text-sm text-text-primary truncate">{trade.name}</div>
          <div className="num text-xs text-text-muted">{trade.ticker}</div>
        </div>
      ),
    },
    {
      key: 'entry',
      header: '진입가',
      width: '110px',
      align: 'right',
      render: (trade) => (
        <div className="text-right">
          <Num value={trade.entry} format="price" tone="neutral" />
          <div className="num text-[11px] text-text-muted">
            {trade.entry_time ? `${fmtTimeHm(trade.entry_time)} 기준` : '-'}
          </div>
        </div>
      ),
    },
    {
      key: 'buy_date',
      header: '매수일',
      width: '100px',
      render: (trade) => (
        <span className="num text-xs text-text-secondary">
          {trade.buy_date ?? trade.date}
        </span>
      ),
    },
    {
      key: 'eval_date',
      header: '평가일',
      width: '100px',
      render: (trade) => (
        <span className="num text-xs text-text-secondary">{trade.eval_date ?? '-'}</span>
      ),
    },
    {
      key: 'eval_08',
      header: '08시 NXT',
      width: '130px',
      align: 'right',
      render: (trade) => (
        <div className="inline-flex items-center gap-1.5 justify-end">
          <Num value={trade.eval_08_price ?? null} format="price" tone="neutral" />
          <OutcomePill outcome={trade.outcome_08} />
        </div>
      ),
    },
    {
      key: 'roi_08',
      header: '08시 손익률',
      width: '90px',
      align: 'right',
      render: (trade) => <Num value={trade.roi_08 ?? null} format="signed-percent" />,
    },
    {
      key: 'eval_09',
      header: '09시 정규장',
      width: '130px',
      align: 'right',
      render: (trade) => (
        <div className="inline-flex items-center gap-1.5 justify-end">
          <Num value={trade.eval_09_price ?? null} format="price" tone="neutral" />
          <OutcomePill outcome={trade.outcome_09} />
        </div>
      ),
    },
    {
      key: 'roi_09',
      header: '09시 손익률',
      width: '90px',
      align: 'right',
      render: (trade) => <Num value={trade.roi_09 ?? null} format="signed-percent" />,
    },
    {
      key: 'score',
      header: '점수',
      width: '60px',
      align: 'right',
      render: (trade) => <Num value={trade.score} format="count" tone="muted" />,
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={trades}
      rowKey={(trade) => trade.key}
      emptyMessage="거래 내역 없음"
      dense
      minWidth="1100px"
    />
  );
}

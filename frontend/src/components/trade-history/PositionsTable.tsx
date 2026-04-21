import React from 'react';
import type { DashboardAccountPosition } from '../../types/api';
import { DataTable, type Column } from '../ui/DataTable';
import { Num } from '../ui/Num';

// Design Ref: Design §4.5 — 매매내역 보유 종목 테이블.

interface PositionsTableProps {
  positions: DashboardAccountPosition[];
}

export function PositionsTable({ positions }: PositionsTableProps) {
  const columns: Column<DashboardAccountPosition>[] = [
    {
      key: 'name',
      header: '종목',
      render: (pos) => (
        <div className="min-w-0">
          <div className="text-sm text-text-primary truncate">{pos.stock_name}</div>
          <div className="num text-xs text-text-muted">{pos.ticker}</div>
        </div>
      ),
    },
    {
      key: 'quantity',
      header: '보유',
      width: '80px',
      align: 'right',
      render: (pos) => <Num value={pos.quantity} format="count" />,
    },
    {
      key: 'available',
      header: '주문가능',
      width: '80px',
      align: 'right',
      render: (pos) => <Num value={pos.available_qty} format="count" tone="muted" />,
    },
    {
      key: 'avg',
      header: '평단가',
      width: '100px',
      align: 'right',
      render: (pos) => <Num value={pos.avg_price} format="price" tone="neutral" />,
    },
    {
      key: 'current',
      header: '현재가',
      width: '100px',
      align: 'right',
      render: (pos) => <Num value={pos.current_price} format="price" tone="neutral" />,
    },
    {
      key: 'profit_rate',
      header: '수익률',
      width: '90px',
      align: 'right',
      render: (pos) => <Num value={pos.profit_rate} format="signed-percent" showArrow />,
    },
    {
      key: 'profit_amount',
      header: '평가손익',
      width: '120px',
      align: 'right',
      render: (pos) => <Num value={pos.profit_amount} format="signed-kr-money" />,
    },
    {
      key: 'eval_amount',
      header: '평가금액',
      width: '120px',
      align: 'right',
      render: (pos) => <Num value={pos.eval_amount} format="kr-money" tone="neutral" />,
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={positions}
      rowKey={(pos) => `${pos.ticker}-${pos.stock_name}`}
      emptyMessage="보유 종목 없음"
      dense
    />
  );
}

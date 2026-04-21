import React from 'react';
import type { TradeHistoryDailyItem } from '../../types/api';
import { DataTable, type Column } from '../ui/DataTable';
import { Num } from '../ui/Num';

// Design Ref: Design §4.5 — 일자별 손익 테이블.

interface DailyPnlTableProps {
  items: TradeHistoryDailyItem[];
}

export function DailyPnlTable({ items }: DailyPnlTableProps) {
  const columns: Column<TradeHistoryDailyItem>[] = [
    {
      key: 'date',
      header: '일자',
      width: '110px',
      render: (item) => <span className="num text-sm text-text-primary">{item.date}</span>,
    },
    {
      key: 'buy',
      header: '매수금액',
      align: 'right',
      render: (item) => <Num value={item.buy_amount} format="kr-money" tone="neutral" />,
    },
    {
      key: 'sell',
      header: '매도금액',
      align: 'right',
      render: (item) => <Num value={item.sell_amount} format="kr-money" tone="neutral" />,
    },
    {
      key: 'realized',
      header: '실현손익',
      align: 'right',
      render: (item) => <Num value={item.realized_profit} format="signed-kr-money" />,
    },
    {
      key: 'commission',
      header: '수수료',
      align: 'right',
      render: (item) => <Num value={item.commission} format="price" tone="muted" />,
    },
    {
      key: 'tax',
      header: '세금',
      align: 'right',
      render: (item) => <Num value={item.tax} format="price" tone="muted" />,
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={items}
      rowKey={(item) => item.date}
      emptyMessage="선택 구간 일자별 손익 없음"
      dense
    />
  );
}

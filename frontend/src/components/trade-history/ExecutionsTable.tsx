import React from 'react';
import type { TradeHistoryExecutionItem } from '../../types/api';
import { DataTable, type Column } from '../ui/DataTable';
import { Num } from '../ui/Num';
import { Badge } from '../ui/Badge';
import { fmtDateTime, fmtCount } from '../../app/formatters';

// Design Ref: Design §4.5 — 체결 내역 테이블.
// Plan 버그 B-06 해결: venue 컬럼 중복 제거 (기존 체결시각 하단 + 전용 컬럼 2회 → 전용 컬럼 1회).
// Plan 버그 B-07 해결: 15 컬럼 → 11 컬럼 축소 + minWidth로 수평 스크롤.

interface ExecutionsTableProps {
  items: TradeHistoryExecutionItem[];
}

function sideVariant(side: string): 'up' | 'down' | 'neutral' {
  const s = side.toUpperCase();
  if (s === 'BUY' || s === '매수') return 'up';
  if (s === 'SELL' || s === '매도') return 'down';
  return 'neutral';
}

export function ExecutionsTable({ items }: ExecutionsTableProps) {
  const columns: Column<TradeHistoryExecutionItem>[] = [
    {
      key: 'time',
      header: '체결시각',
      width: '140px',
      render: (item) => (
        <span className="num text-xs text-text-secondary">
          {item.filled_time ? fmtDateTime(item.filled_time) : '-'}
        </span>
      ),
    },
    {
      key: 'name',
      header: '종목',
      render: (item) => (
        <div className="min-w-0">
          <div className="text-sm text-text-primary truncate">{item.stock_name}</div>
          <div className="num text-xs text-text-muted">{item.ticker}</div>
        </div>
      ),
    },
    {
      key: 'side',
      header: '구분',
      width: '70px',
      render: (item) => (
        <Badge variant={sideVariant(item.side || item.order_type)} size="xs">
          {item.side || item.order_type}
        </Badge>
      ),
    },
    {
      key: 'status',
      header: '상태',
      width: '64px',
      render: (item) => (
        <span className="text-xs text-text-secondary">{item.order_status}</span>
      ),
    },
    {
      key: 'venue',
      header: '거래소',
      width: '64px',
      render: (item) => (
        <span className="text-xs text-text-secondary">{item.venue || '-'}</span>
      ),
    },
    {
      key: 'qty',
      header: '주문/체결',
      width: '110px',
      align: 'right',
      render: (item) => (
        <div className="text-right">
          <Num value={item.filled_qty} format="count" tone="neutral" />
          <div className="num text-[11px] text-text-muted">
            / {fmtCount(item.order_qty)}
            {item.unfilled_qty > 0 ? (
              <span className="text-warn ml-1">(미 {item.unfilled_qty})</span>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      key: 'order_price',
      header: '주문가',
      width: '100px',
      align: 'right',
      render: (item) => <Num value={item.order_price} format="price" tone="muted" />,
    },
    {
      key: 'filled_price',
      header: '체결가',
      width: '100px',
      align: 'right',
      render: (item) => <Num value={item.filled_price} format="price" tone="neutral" />,
    },
    {
      key: 'fee',
      header: '수수료',
      width: '80px',
      align: 'right',
      render: (item) => <Num value={item.fee} format="price" tone="muted" />,
    },
    {
      key: 'tax',
      header: '세금',
      width: '80px',
      align: 'right',
      render: (item) => <Num value={item.tax} format="price" tone="muted" />,
    },
    {
      key: 'slippage',
      header: '슬리피지',
      width: '90px',
      align: 'right',
      render: (item) => <Num value={item.slippage_bps / 100} format="signed-percent" />,
    },
    {
      key: 'order_no',
      header: '주문번호',
      width: '130px',
      render: (item) => (
        <div className="num text-xs text-text-muted truncate">
          <div className="text-text-secondary">{item.order_no}</div>
          {item.original_order_no ? <div>{item.original_order_no}</div> : null}
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={items}
      rowKey={(item) => item.key}
      emptyMessage="선택 구간 체결내역 없음"
      dense
      minWidth="1280px"
    />
  );
}

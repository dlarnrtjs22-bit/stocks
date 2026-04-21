import React from 'react';
import type { GradeSummaryItem } from '../../types/api';
import { DataTable, type Column } from '../ui/DataTable';
import { Num } from '../ui/Num';
import { Badge, gradeVariant } from '../ui/Badge';

// Design Ref: Design §4.4 — 등급별 성과 테이블 (08/09 가로 비교).

interface GradeSummaryTableProps {
  items: GradeSummaryItem[];
}

export function GradeSummaryTable({ items }: GradeSummaryTableProps) {
  const columns: Column<GradeSummaryItem>[] = [
    {
      key: 'grade',
      header: '등급',
      width: '60px',
      render: (item) => <Badge variant={gradeVariant(item.grade)}>{item.grade}</Badge>,
    },
    {
      key: 'count',
      header: '건수',
      width: '70px',
      align: 'right',
      render: (item) => <Num value={item.count} format="count" tone="neutral" />,
    },
    {
      key: 'win_08',
      header: '08시 승률',
      align: 'right',
      render: (item) => (
        <span className="num text-text-primary">{item.win_rate_08}%</span>
      ),
    },
    {
      key: 'roi_08',
      header: '08시 평균 ROI',
      align: 'right',
      render: (item) => <Num value={item.avg_roi_08} format="signed-percent" />,
    },
    {
      key: 'wl_08',
      header: '08시 W/L',
      align: 'right',
      render: (item) => (
        <span className="num text-text-secondary text-xs">{item.wl_08}</span>
      ),
    },
    {
      key: 'win_09',
      header: '09시 승률',
      align: 'right',
      render: (item) => (
        <span className="num text-text-primary">{item.win_rate_09}%</span>
      ),
    },
    {
      key: 'roi_09',
      header: '09시 평균 ROI',
      align: 'right',
      render: (item) => <Num value={item.avg_roi_09} format="signed-percent" />,
    },
    {
      key: 'wl_09',
      header: '09시 W/L',
      align: 'right',
      render: (item) => (
        <span className="num text-text-secondary text-xs">{item.wl_09}</span>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={items}
      rowKey={(item) => item.grade}
      emptyMessage="등급별 집계 데이터 없음"
      dense
    />
  );
}

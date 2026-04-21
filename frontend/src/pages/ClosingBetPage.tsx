import React from 'react';
import { BasisPanel } from '../components/common/BasisPanel';
import { ClosingView } from '../components/closing/ClosingView';
import { KpiStat } from '../components/ui/KpiStat';
import { Num } from '../components/ui/Num';
import type { ClosingBetResponse } from '../types/api';

// Design Ref: Design §4.3 — 종가배팅 페이지 상단 KPI + Basis + View.

function dataStatusLabel(value?: string | null): string {
  const code = String(value || '').toUpperCase();
  if (code === 'UPDATED') return '최신 데이터';
  if (code === 'OLD_DATA') return '이전 거래일 데이터';
  return value || '-';
}

interface ClosingBetPageProps {
  loading: boolean;
  data?: ClosingBetResponse | null;
  onPageChange: (page: number) => void;
}

export function ClosingBetPage({ loading, data, onPageChange }: ClosingBetPageProps) {
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-4 gap-3">
        <KpiStat
          label="전체 후보"
          value={<Num value={data?.candidates_count ?? 0} format="count" tone="neutral" />}
        />
        <KpiStat
          label="매수 가능 시그널"
          value={
            <Num
              value={data?.buyable_signals_count ?? data?.signals_count ?? 0}
              format="count"
              tone="neutral"
            />
          }
        />
        <KpiStat
          label="핵심 관찰 종목"
          value={
            <Num
              value={data?.featured_count ?? data?.featured_items?.length ?? 0}
              format="count"
              tone="neutral"
            />
          }
        />
        <KpiStat
          label="데이터 상태"
          value={<span className="text-base font-semibold">{dataStatusLabel(data?.status)}</span>}
        />
      </div>
      <BasisPanel basis={data?.basis} />
      <ClosingView loading={loading} data={data} onPageChange={onPageChange} />
    </div>
  );
}

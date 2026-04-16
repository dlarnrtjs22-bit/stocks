import React from 'react';
import { BasisPanel } from '../components/common/BasisPanel';
import { PerformanceView } from '../components/performance/PerformanceView';
import type { PerformanceRefreshResponse, PerformanceResponse } from '../types/api';

// 이 페이지는 누적 성과 화면 전체를 렌더링한다.
interface PerformancePageProps {
  loading: boolean;
  data?: PerformanceResponse | null;
  onPageChange: (page: number) => void;
  onQuickRefresh: () => void;
  quickRefreshing: boolean;
  refreshInfo?: PerformanceRefreshResponse | null;
}

export function PerformancePage({ loading, data, onPageChange, onQuickRefresh, quickRefreshing, refreshInfo }: PerformancePageProps) {
  return (
    <div className="section-stack">
      <BasisPanel basis={data?.basis} />
      <PerformanceView loading={loading} data={data} onPageChange={onPageChange} onQuickRefresh={onQuickRefresh} quickRefreshing={quickRefreshing} refreshInfo={refreshInfo} />
    </div>
  );
}

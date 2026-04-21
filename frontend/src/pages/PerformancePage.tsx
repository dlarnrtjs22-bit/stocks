import React from 'react';
import { BasisPanel } from '../components/common/BasisPanel';
import { PerformanceView } from '../components/performance/PerformanceView';
import type { PerformanceRefreshResponse, PerformanceResponse } from '../types/api';

// Design Ref: Design §4.4.
interface PerformancePageProps {
  loading: boolean;
  data?: PerformanceResponse | null;
  onPageChange: (page: number) => void;
  onQuickRefresh: () => void;
  quickRefreshing: boolean;
  refreshInfo?: PerformanceRefreshResponse | null;
}

export function PerformancePage({
  loading,
  data,
  onPageChange,
  onQuickRefresh,
  quickRefreshing,
  refreshInfo,
}: PerformancePageProps) {
  return (
    <div className="flex flex-col gap-3">
      <BasisPanel basis={data?.basis} />
      <PerformanceView
        loading={loading}
        data={data}
        onPageChange={onPageChange}
        onQuickRefresh={onQuickRefresh}
        quickRefreshing={quickRefreshing}
        refreshInfo={refreshInfo}
      />
    </div>
  );
}

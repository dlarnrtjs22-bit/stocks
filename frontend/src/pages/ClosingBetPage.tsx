import React from 'react';
import { BasisPanel } from '../components/common/BasisPanel';
import { ClosingView } from '../components/closing/ClosingView';
import type { ClosingBetResponse } from '../types/api';


function dataStatusLabel(value?: string | null): string {
  const code = String(value || '').toUpperCase();
  if (code === 'UPDATED') return '최신 데이터';
  if (code === 'OLD_DATA') return '이전 거래일 데이터';
  return value || '-';
}

// 이 페이지는 종가배팅 화면 상단 KPI 와 본문을 그린다.
interface ClosingBetPageProps {
  loading: boolean;
  data?: ClosingBetResponse | null;
  onPageChange: (page: number) => void;
}

export function ClosingBetPage({ loading, data, onPageChange }: ClosingBetPageProps) {
  return (
    <div className="section-stack">
      <div className="metric-box-row four">
        <div className="metric-box"><div className="metric-label">전체 후보</div><div className="metric-value">{data?.candidates_count ?? 0}</div></div>
        <div className="metric-box"><div className="metric-label">매수 가능 시그널</div><div className="metric-value">{data?.buyable_signals_count ?? data?.signals_count ?? 0}</div></div>
        <div className="metric-box"><div className="metric-label">핵심 관찰 종목</div><div className="metric-value">{data?.featured_count ?? data?.featured_items?.length ?? 0}</div></div>
        <div className="metric-box"><div className="metric-label">데이터 상태</div><div className="metric-value">{dataStatusLabel(data?.status)}</div></div>
      </div>
      <BasisPanel basis={data?.basis} />
      <ClosingView loading={loading} data={data} onPageChange={onPageChange} />
    </div>
  );
}

import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import type { DashboardResponse } from '../../types/api';
import { Panel } from '../ui/Panel';
import { MarketStrip } from './MarketStrip';
import { PicksTable } from './PicksTable';
import { PickDetailPanel } from './PickDetailPanel';

// Design Ref: Design §4.2 — 마스터/디테일 컨테이너.
// Plan SC-01: Trading Pro 스타일 적용. SC-10: 기존 기능(새로고침/추천 5종목) 보존.

interface DashboardViewProps {
  loading: boolean;
  data?: DashboardResponse | null;
  onRefresh: () => void;
  dashboardRefreshing: boolean;
}

export function DashboardView({
  loading,
  data,
  onRefresh,
  dashboardRefreshing,
}: DashboardViewProps) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  // 데이터 로드 시 첫 종목 자동 선택
  useEffect(() => {
    if (!data?.picks || data.picks.length === 0) {
      setSelectedTicker(null);
      return;
    }
    const exists = data.picks.some((p) => p.ticker === selectedTicker);
    if (!exists) {
      setSelectedTicker(data.picks[0].ticker);
    }
  }, [data]);

  if (loading && !data) {
    return (
      <Panel tone="default">
        <div className="text-text-secondary text-sm">대시보드 데이터를 불러오는 중입니다.</div>
      </Panel>
    );
  }
  if (!data) {
    return (
      <Panel tone="default">
        <div className="text-text-secondary text-sm">대시보드 데이터가 없습니다.</div>
      </Panel>
    );
  }

  const selectedPick = data.picks.find((p) => p.ticker === selectedTicker) ?? null;
  const updatedAt = data.markets[0]?.snapshot_time ?? null;

  return (
    <div className="flex flex-col gap-3 min-h-[calc(100vh-5rem)]">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-text-muted">
          {data.date ? <>기준일 <span className="num text-text-secondary">{data.date}</span></> : null}
          {data.market_summary ? (
            <span className="ml-3 text-text-secondary">{data.market_summary}</span>
          ) : null}
        </div>
        <button
          onClick={onRefresh}
          disabled={dashboardRefreshing}
          className={clsx(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-medium transition-colors',
            'border-border bg-surface text-text-primary hover:bg-elevated',
            dashboardRefreshing && 'opacity-60 cursor-not-allowed',
          )}
        >
          <RefreshCw size={12} className={clsx(dashboardRefreshing && 'animate-spin')} />
          {dashboardRefreshing ? '새로고침 중' : '새로고침'}
        </button>
      </div>

      {/* Market Strip */}
      <MarketStrip markets={data.markets} updatedAt={updatedAt} />

      {/* Master / Detail */}
      <div className="grid grid-cols-[minmax(0,8fr)_minmax(0,4fr)] gap-3 flex-1 min-h-0">
        <Panel
          tone="default"
          padding="none"
          title={
            <span>
              추천 후보
              <span className="ml-1.5 text-text-muted text-sm font-normal">
                {data.picks.length}종목
              </span>
            </span>
          }
          subtitle={
            data.picks.length < 5
              ? `가격과 조건을 충족한 ${data.picks.length}종목만 추렸습니다.`
              : undefined
          }
          className="overflow-hidden flex flex-col"
        >
          <div className="overflow-y-auto">
            <PicksTable
              picks={data.picks}
              selectedTicker={selectedTicker}
              onSelect={setSelectedTicker}
            />
          </div>
        </Panel>

        <PickDetailPanel pick={selectedPick} />
      </div>
    </div>
  );
}

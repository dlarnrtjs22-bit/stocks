import React from 'react';
import clsx from 'clsx';
import { RefreshCw } from 'lucide-react';
import type { PerformanceRefreshResponse, PerformanceResponse } from '../../types/api';
import { Panel } from '../ui/Panel';
import { KpiStat } from '../ui/KpiStat';
import { Num } from '../ui/Num';
import { Pager } from '../common/Pager';
import { GradeSummaryTable } from './GradeSummaryTable';
import { PerformanceTradeTable } from './PerformanceTradeTable';

// Design Ref: Design §4.4 — KPI 스트립 + 등급 테이블 + 메인 테이블.

interface PerformanceViewProps {
  loading: boolean;
  data?: PerformanceResponse | null;
  onPageChange: (page: number) => void;
  onQuickRefresh: () => void;
  quickRefreshing: boolean;
  refreshInfo?: PerformanceRefreshResponse | null;
}

export function PerformanceView({
  loading,
  data,
  onPageChange,
  onQuickRefresh,
  quickRefreshing,
  refreshInfo,
}: PerformanceViewProps) {
  if (loading && !data) {
    return (
      <Panel tone="default">
        <div className="text-text-secondary text-sm">누적 성과 데이터를 불러오는 중입니다.</div>
      </Panel>
    );
  }
  if (!data) {
    return (
      <Panel tone="default">
        <div className="text-text-secondary text-sm">데이터 없음</div>
      </Panel>
    );
  }

  const betterLabel =
    data.comparison.better_slot === '08'
      ? '08시 NXT 우세'
      : data.comparison.better_slot === '09'
        ? '09시 정규장 우세'
        : '동률/평가대기';
  const betterTone: 'up' | 'down' | 'default' =
    data.comparison.better_slot === '08'
      ? 'up'
      : data.comparison.better_slot === '09'
        ? 'down'
        : 'default';
  const isRolling7d = data.basis?.request_date === 'latest(7d)';

  return (
    <div className="flex flex-col gap-3">
      {isRolling7d ? (
        <div className="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-secondary">
          누적 성과 기본 조회는 금일 포함 최근 7거래일 기준입니다.
        </div>
      ) : null}

      {/* KPI Strip */}
      <div className="grid grid-cols-4 gap-3">
        <KpiStat
          label="Total Signals"
          value={<span className="num">{data.summary.total_signals}</span>}
        />
        <KpiStat
          label="08시 NXT 승률"
          value={<span className="num">{data.summary_08.win_rate}%</span>}
          delta={
            <>
              W/L <span className="num">{data.summary_08.wins}/{data.summary_08.losses}</span>
              {' · 평균 '}
              <Num value={data.summary_08.avg_roi} format="signed-percent" className="inline" />
            </>
          }
        />
        <KpiStat
          label="09시 정규장 승률"
          value={<span className="num">{data.summary_09.win_rate}%</span>}
          delta={
            <>
              W/L <span className="num">{data.summary_09.wins}/{data.summary_09.losses}</span>
              {' · 평균 '}
              <Num value={data.summary_09.avg_roi} format="signed-percent" className="inline" />
            </>
          }
        />
        <KpiStat
          label="비교 (Edge)"
          tone={betterTone}
          value={<span className="text-base font-semibold">{betterLabel}</span>}
          delta={
            <>
              승률 차이 <span className="num">{data.comparison.edge_pct}%p</span>
            </>
          }
        />
      </div>

      {/* Grade Summary */}
      <Panel
        tone="default"
        padding="none"
        title="등급별 성과"
        subtitle="08시 / 09시 비교"
      >
        <GradeSummaryTable items={data.grade_summary} />
      </Panel>

      {/* Main Trade Table */}
      <Panel
        tone="default"
        padding="none"
        title="거래 내역"
        subtitle="추천가 대비 다음 거래일 08시/09시 평가"
        action={
          <button
            onClick={onQuickRefresh}
            disabled={quickRefreshing}
            className={clsx(
              'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
              'bg-brand hover:bg-brand-hover text-white',
              quickRefreshing && 'opacity-60 cursor-not-allowed',
            )}
          >
            <RefreshCw size={12} className={clsx(quickRefreshing && 'animate-spin')} />
            {quickRefreshing ? '갱신 중' : '비교값 빠른갱신'}
          </button>
        }
      >
        {refreshInfo ? (
          <div className="border-b border-border-subtle bg-base px-3 py-2 text-xs text-text-secondary">
            {refreshInfo.message} · 08시 갱신{' '}
            <span className="num">{refreshInfo.refreshed_08}</span>건 · 09시 갱신{' '}
            <span className="num">{refreshInfo.refreshed_09}</span>건 · 추적{' '}
            <span className="num">{refreshInfo.tracked_count}</span>종목
          </div>
        ) : null}
        <PerformanceTradeTable trades={data.trades} />
      </Panel>

      <Pager
        page={data.pagination.page}
        totalPages={data.pagination.total_pages}
        onChange={onPageChange}
      />
    </div>
  );
}

import React from 'react';
import type { TradeHistoryResponse } from '../../types/api';
import { Panel } from '../ui/Panel';
import { KpiStat } from '../ui/KpiStat';
import { Num } from '../ui/Num';
import { PositionsTable } from './PositionsTable';
import { DailyPnlTable } from './DailyPnlTable';
import { ExecutionsTable } from './ExecutionsTable';
import { fmtDateTime } from '../../app/formatters';

// Design Ref: Design §4.5 (updated by Act-1) — KPI 바 + 3섹션 동시 표시.
// Act-1 피드백: Tab 방식은 비교 워크플로에 불편 → 3개 섹션(보유/일자별/체결)을 세로 3단으로 다시 표시.

interface TradeHistoryViewProps {
  loading: boolean;
  data?: TradeHistoryResponse | null;
}

export function TradeHistoryView({ loading, data }: TradeHistoryViewProps) {
  if (loading && !data) {
    return (
      <Panel tone="default">
        <div className="text-text-secondary text-sm">매매내역 데이터를 불러오는 중입니다.</div>
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

  const account = data.account;
  const profitTone: 'up' | 'down' | 'default' =
    account.total_eval_profit > 0
      ? 'up'
      : account.total_eval_profit < 0
        ? 'down'
        : 'default';
  const realizedTone: 'up' | 'down' | 'default' =
    account.realized_profit > 0
      ? 'up'
      : account.realized_profit < 0
        ? 'down'
        : 'default';

  return (
    <div className="flex flex-col gap-3">
      {/* KPI Strip */}
      <div className="grid grid-cols-4 gap-3">
        <KpiStat
          label="평가금액"
          value={<Num value={account.total_eval_amt} format="kr-money" tone="neutral" />}
        />
        <KpiStat
          label="평가손익"
          tone={profitTone}
          value={<Num value={account.total_eval_profit} format="signed-kr-money" />}
          delta={
            <Num value={account.total_profit_rate} format="signed-percent" className="inline" />
          }
        />
        <KpiStat
          label="실현손익"
          tone={realizedTone}
          value={<Num value={account.realized_profit} format="signed-kr-money" />}
        />
        <KpiStat
          label="추정자산"
          value={<Num value={account.estimated_assets} format="kr-money" tone="neutral" />}
        />
      </div>

      {/* Account meta */}
      <div className="flex items-center justify-between flex-wrap gap-2 text-xs text-text-secondary">
        <div className="flex items-center gap-3">
          <span>
            계좌 <span className="num text-text-primary">{account.account_no || '-'}</span>
          </span>
          <span>
            보유 <span className="num text-text-primary">{account.holdings_count}</span>종목
          </span>
          <span>
            미체결 <span className="num text-text-primary">{account.unfilled_count}</span>건
          </span>
          <span>
            체결 <span className="num text-text-primary">{data.executions.length}</span>건
          </span>
        </div>
        <div className="text-text-muted">
          갱신 {fmtDateTime(data.refreshed_at || account.snapshot_time || null)}
        </div>
      </div>

      {account.note ? (
        <div className="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs text-text-secondary">
          {account.note}
        </div>
      ) : null}

      {/* 3단: 보유 종목 */}
      <Panel
        tone="default"
        padding="none"
        title="보유 종목"
        subtitle={`${account.positions.length}종목`}
      >
        <PositionsTable positions={account.positions} />
      </Panel>

      {/* 3단: 일자별 손익 */}
      <Panel
        tone="default"
        padding="none"
        title="일자별 손익"
        subtitle={`${data.daily_summary.length}일`}
      >
        <DailyPnlTable items={data.daily_summary} />
      </Panel>

      {/* 3단: 체결 내역 */}
      <Panel
        tone="default"
        padding="none"
        title="체결 내역"
        subtitle={`${data.executions.length}건`}
      >
        <ExecutionsTable items={data.executions} />
      </Panel>
    </div>
  );
}

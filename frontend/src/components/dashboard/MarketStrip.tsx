import React from 'react';
import clsx from 'clsx';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { DashboardMarketItem } from '../../types/api';
import { Num } from '../ui/Num';
import { fmtDateTime, fmtPrice } from '../../app/formatters';

// Design Ref: Design §4.2 — 상단 시장 스트립.

interface MarketStripProps {
  markets: DashboardMarketItem[];
  updatedAt?: string | null;
}

function trendIcon(changePct: number) {
  if (changePct > 0) return <TrendingUp size={14} className="text-up" />;
  if (changePct < 0) return <TrendingDown size={14} className="text-down" />;
  return <Minus size={14} className="text-flat" />;
}

export function MarketStrip({ markets, updatedAt }: MarketStripProps) {
  if (!markets || markets.length === 0) {
    return (
      <div className="border border-border-subtle rounded-md bg-surface px-3 py-2 text-sm text-text-muted">
        시장 데이터 없음
      </div>
    );
  }

  return (
    <div className="border border-border-subtle rounded-md bg-surface">
      <div
        className={clsx(
          'grid gap-px bg-border-subtle',
          markets.length === 1 && 'grid-cols-1',
          markets.length === 2 && 'grid-cols-2',
          markets.length === 3 && 'grid-cols-3',
          markets.length >= 4 && 'grid-cols-4',
        )}
      >
        {markets.map((market) => (
          <div
            key={market.market}
            className="flex flex-col gap-1 bg-surface px-3 py-2.5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-text-secondary uppercase tracking-wide">
                {market.market_label}
              </span>
              {trendIcon(market.change_pct)}
            </div>
            <div className="flex items-baseline gap-2">
              <span className="num text-xl font-semibold text-text-primary">
                {fmtPrice(Math.round(market.index_value))}
              </span>
              <Num value={market.change_pct} format="signed-percent" className="text-sm font-medium" />
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-up">
                ▲ <Num value={market.rise_count} format="count" tone="muted" className="text-up" />
              </span>
              <span className="text-down">
                ▼ <Num value={market.fall_count} format="count" tone="muted" className="text-down" />
              </span>
              <span className="text-text-muted">
                프로그램 <Num value={market.total_net} format="signed-eok" />
              </span>
            </div>
          </div>
        ))}
      </div>
      {updatedAt ? (
        <div className="border-t border-border-subtle px-3 py-1.5 text-[11px] text-text-muted">
          업데이트 {fmtDateTime(updatedAt)}
        </div>
      ) : null}
    </div>
  );
}

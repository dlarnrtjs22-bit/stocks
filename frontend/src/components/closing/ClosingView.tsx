import React, { useMemo, useState } from 'react';
import type { ClosingBetItem, ClosingBetResponse } from '../../types/api';
import { Panel } from '../ui/Panel';
import { Badge, type BadgeVariant } from '../ui/Badge';
import { Pager } from '../common/Pager';
import { ClosingTable, type ClosingTableRow } from './ClosingTable';
import { ClosingDetailDrawer } from './ClosingDetailDrawer';

// Act-1 피드백: Dashboard처럼 "기준일 · 최신 데이터" 배지를 크게 표시.
function statusBadge(status: string | undefined | null): {
  label: string;
  variant: BadgeVariant;
} {
  const code = String(status || '').toUpperCase();
  if (code === 'UPDATED') return { label: '최신 데이터', variant: 'success' };
  if (code === 'OLD_DATA') return { label: '이전 거래일 데이터', variant: 'warn' };
  if (!code) return { label: '상태 미확인', variant: 'neutral' };
  return { label: status || '-', variant: 'neutral' };
}

// Design Ref: Design §4.3 — 종가배팅 테이블 + Drawer 컨테이너.

interface ClosingViewProps {
  loading: boolean;
  data?: ClosingBetResponse | null;
  onPageChange: (page: number) => void;
}

export function ClosingView({ loading, data, onPageChange }: ClosingViewProps) {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { rows, itemsByTicker } = useMemo(() => {
    if (!data)
      return {
        rows: [] as ClosingTableRow[],
        itemsByTicker: new Map<string, ClosingBetItem>(),
      };
    // Act-1 fix: featured_items는 items에 포함되지 않는 별개 배열이므로
    // 모든 페이지 상단에 ★ Featured 5종목을 고정 표시하고, 그 아래 pagination된 items를 이어 붙인다.
    // 이전 버그: items만 렌더 → S등급 삼성SDI 등 Featured 최상위 종목이 테이블에서 사라짐.
    const featuredTickers = new Set(data.featured_items.map((item) => item.ticker));
    const pageOffset = Math.max(0, (data.pagination.page - 1) * data.pagination.page_size);
    const map = new Map<string, ClosingBetItem>();

    const featuredRows: ClosingTableRow[] = data.featured_items.map((item, index) => {
      map.set(item.ticker, item);
      return {
        ...item,
        isFeatured: true,
        displayRank: index + 1,
      };
    });
    const itemRows: ClosingTableRow[] = data.items
      .filter((item) => !featuredTickers.has(item.ticker))
      .map((item, index) => {
        map.set(item.ticker, item);
        return {
          ...item,
          isFeatured: false,
          displayRank: pageOffset + index + 1 + featuredRows.length,
        };
      });
    return { rows: [...featuredRows, ...itemRows], itemsByTicker: map };
  }, [data]);

  const selectedItem = selectedTicker ? itemsByTicker.get(selectedTicker) ?? null : null;

  const handleSelect = (ticker: string) => {
    setSelectedTicker(ticker);
    setDrawerOpen(true);
  };
  const handleCloseDrawer = () => setDrawerOpen(false);

  if (loading && !data) {
    return (
      <Panel tone="default">
        <div className="text-text-secondary text-sm">종가배팅 데이터를 불러오는 중입니다.</div>
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

  const featuredCount = data.featured_items.length;
  const buyableCount = data.buyable_signals_count ?? 0;
  const status = statusBadge(data.status);

  return (
    <div className="flex flex-col gap-3">
      {/* 기준일 + 상태 배지 (Dashboard와 동일한 prominence) */}
      <div className="flex items-center justify-between flex-wrap gap-3 rounded-md border border-border-subtle bg-surface px-3 py-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-text-muted uppercase tracking-wide">기준일</span>
          <span className="num text-md font-semibold text-text-primary">{data.date || '-'}</span>
          <Badge variant={status.variant} size="sm">
            {status.label}
          </Badge>
          {data.is_today ? (
            <Badge variant="info" size="sm">TODAY</Badge>
          ) : null}
        </div>
        <div className="flex items-center gap-3 text-xs text-text-secondary">
          <span>
            전체 <span className="num text-text-primary">{data.pagination.total}</span>건
          </span>
          <span>
            Featured <span className="num text-warn">★ {featuredCount}</span>
          </span>
          <span>
            Buyable <span className="num text-text-primary">{buyableCount}</span>
          </span>
        </div>
      </div>

      <Panel
        tone="default"
        padding="none"
        title="종가배팅 후보"
        subtitle="★ 표시는 Featured 5종목 · 행 클릭 시 상세 패널"
      >
        <ClosingTable
          rows={rows}
          selectedTicker={drawerOpen ? selectedTicker : null}
          onSelect={handleSelect}
        />
      </Panel>

      <Pager
        page={data.pagination.page}
        totalPages={data.pagination.total_pages}
        onChange={onPageChange}
      />

      <ClosingDetailDrawer
        item={selectedItem}
        open={drawerOpen}
        onClose={handleCloseDrawer}
      />
    </div>
  );
}

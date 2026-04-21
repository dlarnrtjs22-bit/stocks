import React from 'react';
import { ExternalLink } from 'lucide-react';
import type { ClosingBetItem } from '../../types/api';
import { Drawer } from '../ui/Drawer';
import { Num } from '../ui/Num';
import { Badge, gradeVariant } from '../ui/Badge';
import { ScoreBar } from '../ui/ScoreBar';
import { fmtPrice } from '../../app/formatters';

// Design Ref: Design §4.3 — 종가배팅 상세 드로어.
// Plan 버그 B-02/B-12 해결.

const scoreLabels: Record<string, string> = {
  news: '뉴스',
  news_attention: '화제성',
  supply: '수급',
  chart: '차트',
  volume: '거래량',
  candle: '캔들',
  consolidation: '기간조정',
  market: '시황',
  program: '프로그램',
  sector: '섹터',
  leader: '대장주',
  intraday: '장중 압력',
  foreign: '외국인',
  institution: '기관',
  external: '글로벌',
  technical: '기술',
  momentum: '모멘텀',
};

function scoreLabel(key: string): string {
  return scoreLabels[key] ?? key;
}

interface ClosingDetailDrawerProps {
  item: ClosingBetItem | null;
  open: boolean;
  onClose: () => void;
}

function PriceRow({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: 'warm' | 'cool';
}) {
  const color =
    accent === 'warm' ? 'text-warn' : accent === 'cool' ? 'text-info' : 'text-text-primary';
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={`num text-sm ${color}`}>{fmtPrice(value)}</span>
    </div>
  );
}

function MetricRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}

export function ClosingDetailDrawer({ item, open, onClose }: ClosingDetailDrawerProps) {
  if (!item) {
    return <Drawer open={open} onClose={onClose} width="lg" />;
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width="lg"
      title={
        <span className="inline-flex items-center gap-2">
          <span className="truncate">{item.name}</span>
          <Badge variant={gradeVariant(item.grade)} size="xs">
            {item.grade}
          </Badge>
          <Badge variant="neutral" size="xs">
            {item.market}
          </Badge>
        </span>
      }
      subtitle={
        <span>
          <span className="num">{item.ticker}</span>
          {' · '}현재가 <span className="num text-text-primary">{fmtPrice(item.current_price)}</span>
          {' · '}
          <Num value={item.change_pct} format="signed-percent" showArrow className="text-sm" />
        </span>
      }
    >
      <div className="space-y-4">
        <section>
          <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
            가격
          </h4>
          <div className="rounded-md border border-border-subtle bg-base p-2.5">
            <PriceRow label="진입가" value={item.entry_price} />
            <PriceRow label="현재가" value={item.current_price} />
            <PriceRow label="목표가" value={item.target_price} accent="warm" />
            <PriceRow label="손절가" value={item.stop_price} accent="cool" />
          </div>
        </section>

        <section>
          <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
            수급 · 거래대금
          </h4>
          <div className="grid grid-cols-2 gap-x-3 rounded-md border border-border-subtle bg-base p-2.5">
            <MetricRow
              label="외인 당일"
              value={<Num value={item.foreign_1d} format="signed-kr-money" />}
            />
            <MetricRow
              label="기관 당일"
              value={<Num value={item.inst_1d} format="signed-kr-money" />}
            />
            <MetricRow
              label="외인 5일"
              value={<Num value={item.foreign_5d} format="signed-kr-money" />}
            />
            <MetricRow
              label="기관 5일"
              value={<Num value={item.inst_5d} format="signed-kr-money" />}
            />
            <MetricRow
              label="거래대금"
              value={<Num value={item.trading_value} format="kr-money" tone="neutral" />}
            />
            <MetricRow
              label="점수"
              value={
                <span className="num text-text-primary">
                  {item.score_total}
                  <span className="text-text-muted">/{item.score_max}</span>
                </span>
              }
            />
          </div>
        </section>

        <section>
          <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
            점수 분해
          </h4>
          <div className="rounded-md border border-border-subtle bg-base p-2.5 space-y-2">
            {Object.entries(item.scores).map(([key, value]) => (
              <ScoreBar
                key={key}
                value={value}
                max={3}
                label={scoreLabel(key)}
                compact
              />
            ))}
          </div>
        </section>

        {item.themes && item.themes.length > 0 ? (
          <section>
            <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
              테마
            </h4>
            <div className="flex flex-wrap gap-1">
              {item.themes.map((theme, index) => (
                <span
                  key={`${item.ticker}-theme-${index}`}
                  className="inline-flex items-center px-2 py-0.5 rounded-sm border border-border-subtle bg-base text-xs text-text-secondary"
                >
                  {theme}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {item.ai_analysis ? (
          <section>
            <div className="flex items-center gap-2 mb-1.5">
              <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide">
                AI 종합 분석
              </h4>
              <Badge
                variant={item.analysis_status === 'OK' ? 'success' : 'neutral'}
                size="xs"
              >
                {item.analysis_status_label || item.analysis_status}
              </Badge>
              <Badge
                variant={item.ai_opinion === '매수' ? 'up' : 'down'}
                size="xs"
              >
                의견: {item.ai_opinion}
              </Badge>
              <Badge variant="neutral" size="xs">
                판정: {item.decision_label || item.decision_status}
              </Badge>
            </div>
            <div className="rounded-md border border-border-subtle bg-base p-2.5 text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
              {item.ai_analysis}
            </div>
          </section>
        ) : null}

        <section>
          <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
            컨텍스트
          </h4>
          <div className="rounded-md border border-border-subtle bg-base p-2.5 space-y-1">
            <MetricRow
              label="시황"
              value={
                <span className="text-text-primary text-sm">
                  {String(item.market_context.market_label || item.market || '-')} /{' '}
                  <span className="text-text-secondary">
                    {item.market_status_label || String(item.market_context.market_status || '-')}
                  </span>
                </span>
              }
            />
            <MetricRow
              label="프로그램(시장)"
              value={<Num value={Number(item.program_context.total_net || 0)} format="signed-eok" />}
            />
            <MetricRow
              label="개별 프로그램 순매수"
              value={
                <Num
                  value={Number(item.stock_program_context.latest_net_buy_amt || 0)}
                  format="signed-eok"
                />
              }
            />
            <MetricRow
              label="10분 변화"
              value={
                <Num
                  value={Number(item.stock_program_context.delta_10m_amt || 0)}
                  format="signed-eok"
                />
              }
            />
            <MetricRow
              label="30분 변화"
              value={
                <Num
                  value={Number(item.stock_program_context.delta_30m_amt || 0)}
                  format="signed-eok"
                />
              }
            />
            <MetricRow
              label="글로벌"
              value={
                <span className="text-text-primary text-sm">
                  {item.external_market_status_label ||
                    String(item.external_market_context.status || '-')}{' '}
                  <span className="text-text-muted">
                    · 위험{' '}
                    <span className="num">
                      {Number(item.external_market_context.risk_score || 0).toFixed(1)}
                    </span>
                  </span>
                </span>
              }
            />
            <MetricRow
              label="분봉 패턴"
              value={
                <span className="text-text-primary text-sm">
                  {item.minute_pattern_label || '-'}
                </span>
              }
            />
          </div>
        </section>

        {item.references && item.references.length > 0 ? (
          <section>
            <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
              최근 뉴스
            </h4>
            <div className="space-y-1">
              {item.references.map((ref, index) => (
                <a
                  key={`${item.ticker}-ref-${index}`}
                  href={String(ref.url || '#')}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-start gap-1.5 text-sm text-text-secondary hover:text-brand transition-colors"
                >
                  <ExternalLink size={12} className="mt-1 shrink-0" />
                  <span className="min-w-0">
                    <span className="text-text-muted">[{String(ref.source || 'Naver')}]</span>{' '}
                    {String(ref.title || '')}
                  </span>
                </a>
              ))}
            </div>
          </section>
        ) : null}

        {item.chart_url ? (
          <section>
            <a
              href={item.chart_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border bg-surface hover:bg-elevated text-sm text-text-primary transition-colors"
            >
              <ExternalLink size={12} />
              차트 보기
            </a>
          </section>
        ) : null}
      </div>
    </Drawer>
  );
}

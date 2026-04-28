import React from 'react';
import { ExternalLink } from 'lucide-react';
import type { DashboardPickPayload } from '../../types/api';
import { Num } from '../ui/Num';
import { Badge, gradeVariant } from '../ui/Badge';
import { fmtPrice } from '../../app/formatters';

// Design Ref: Design §4.2 — 선택 종목 상세 (디테일).

interface PickDetailPanelProps {
  pick: DashboardPickPayload | null;
}

function MetricRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}

export function PickDetailPanel({ pick }: PickDetailPanelProps) {
  if (!pick) {
    return (
      <div className="rounded-md border border-border-subtle bg-surface h-full grid place-items-center p-6">
        <div className="text-center">
          <div className="text-sm text-text-secondary mb-1">종목 선택</div>
          <div className="text-xs text-text-muted">
            왼쪽 테이블에서 종목을 클릭하면 상세가 표시됩니다.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-border-subtle bg-surface h-full flex flex-col min-w-0">
      <header className="px-3 py-2.5 border-b border-border-subtle shrink-0">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-md font-semibold text-text-primary truncate">{pick.name}</h3>
              <Badge variant={gradeVariant(pick.grade)} size="xs">
                진입 {pick.grade}
              </Badge>
              <Badge variant={gradeVariant(pick.quality_grade)} size="xs">
                퀄리티 {pick.quality_grade}
              </Badge>
              <Badge variant="neutral" size="xs">
                {pick.market}
              </Badge>
              {pick.sector ? (
                <Badge variant="neutral" size="xs">
                  {pick.sector}
                </Badge>
              ) : null}
            </div>
            <div className="num text-xs text-text-muted mt-0.5">{pick.ticker}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="num text-lg font-semibold text-text-primary leading-none">
              {fmtPrice(pick.current_price)}
            </div>
            <Num
              value={pick.change_pct}
              format="signed-percent"
              showArrow
              className="text-sm"
            />
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        <section>
          <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
            수급
          </h4>
          <div className="grid grid-cols-2 gap-x-3 rounded-md border border-border-subtle bg-base p-2.5">
            <MetricRow
              label="외인 당일"
              value={<Num value={pick.foreign_1d} format="signed-kr-money" />}
            />
            <MetricRow
              label="기관 당일"
              value={<Num value={pick.inst_1d} format="signed-kr-money" />}
            />
            <MetricRow
              label="외인 5일"
              value={<Num value={pick.foreign_5d} format="signed-kr-money" />}
            />
            <MetricRow
              label="기관 5일"
              value={<Num value={pick.inst_5d} format="signed-kr-money" />}
            />
            <MetricRow
              label="거래대금"
              value={<Num value={pick.trading_value} format="kr-money" tone="neutral" />}
            />
            <MetricRow
              label="거래소"
              value={<span className="text-text-primary text-sm">{pick.venue || '-'}</span>}
            />
            <MetricRow
              label="점수"
              value={<span className="num text-text-primary">{pick.score_total}</span>}
            />
            <MetricRow
              label="점수퀄리티"
              value={<Badge variant={gradeVariant(pick.quality_grade)} size="xs">{pick.quality_label || pick.quality_grade}</Badge>}
            />
          </div>
        </section>

        {pick.report_title || pick.report_body || pick.ai_summary ? (
          <section>
            <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
              {pick.report_title || 'AI 리포트'}
            </h4>
            <div className="rounded-md border border-border-subtle bg-base p-2.5 text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
              {pick.report_body || pick.ai_summary || '-'}
            </div>
          </section>
        ) : null}

        {pick.key_points && pick.key_points.length > 0 ? (
          <section>
            <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
              핵심 포인트
            </h4>
            <ul className="space-y-1">
              {pick.key_points.map((point, index) => (
                <li
                  key={`${pick.ticker}-kp-${index}`}
                  className="flex gap-2 text-sm text-text-primary"
                >
                  <span className="text-brand shrink-0">·</span>
                  <span className="min-w-0">{point}</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {pick.intraday ? (
          <section>
            <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
              장중 압력
            </h4>
            <div className="rounded-md border border-border-subtle bg-base p-2.5 space-y-1">
              <MetricRow
                label="호가 불균형"
                value={String(pick.intraday.orderbook_imbalance ?? '-')}
              />
              <MetricRow
                label="체결강도"
                value={String(pick.intraday.execution_strength ?? '-')}
              />
              <MetricRow
                label="분봉 패턴"
                value={pick.minute_pattern_label || String(pick.intraday.minute_pattern ?? '-')}
              />
            </div>
          </section>
        ) : null}

        {pick.references && pick.references.length > 0 ? (
          <section>
            <h4 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-1.5">
              참고 뉴스
            </h4>
            <div className="space-y-1">
              {pick.references.map((ref, index) => (
                <a
                  key={`${pick.ticker}-ref-${index}`}
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
      </div>
    </div>
  );
}

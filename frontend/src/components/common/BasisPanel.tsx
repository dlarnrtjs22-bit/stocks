import React from 'react';
import clsx from 'clsx';
import { fmtDateTime } from '../../app/formatters';
import type { BasisPayload } from '../../types/api';
import { Panel } from '../ui/Panel';
import { Badge } from '../ui/Badge';

// Design Ref: Design §11.2 — 현재 화면 기준(run) 정보.

function BasisMetric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-text-muted">{label}</div>
      <div className="num text-sm text-text-primary truncate">{value}</div>
    </div>
  );
}

export function BasisPanel({ basis }: { basis?: BasisPayload | null }) {
  if (!basis) return null;

  return (
    <Panel
      tone="default"
      padding="md"
      title="Display Basis"
      subtitle={
        <>
          query=<span className="num">{basis.request_date}</span> · run_date=
          <span className="num">{basis.selected_date}</span>
        </>
      }
      action={
        <Badge variant={basis.stale_against_inputs ? 'danger' : 'success'} size="xs">
          {basis.stale_against_inputs ? 'STALE' : 'IN SYNC'}
        </Badge>
      }
    >
      <div className="grid grid-cols-4 gap-3">
        <BasisMetric label="Run Updated" value={fmtDateTime(basis.run_updated_at)} />
        <BasisMetric label="Input Max" value={basis.reference_data_time || '-'} />
        <BasisMetric label="AI Model" value={basis.llm_model || basis.llm_provider || '-'} />
        <BasisMetric
          label="AI Calls"
          value={`${basis.llm_calls_used} / ${basis.overall_ai_top_k}`}
        />
      </div>

      {basis.stale_against_inputs && basis.stale_reason ? (
        <div
          className={clsx(
            'mt-3 rounded-md border border-warn/30 bg-warn/10 px-2.5 py-2 text-xs text-warn',
          )}
        >
          {basis.stale_reason}
        </div>
      ) : null}

      {basis.sources && basis.sources.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
          {basis.sources.map((source) => (
            <div
              key={source.label}
              className="flex items-center gap-1.5 text-xs text-text-secondary"
            >
              <span className="text-text-muted">{source.label}</span>
              <span className="text-text-primary">{source.status}</span>
              <span className="num text-text-muted">{fmtDateTime(source.updated_at)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}

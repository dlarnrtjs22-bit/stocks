import React from 'react';
import { fmtDateTime } from '../../app/formatters';
import type { BasisPayload } from '../../types/api';

// 이 컴포넌트는 현재 화면이 어떤 run 기준으로 만들어졌는지 보여 준다.
export function BasisPanel({ basis }: { basis?: BasisPayload | null }) {
  if (!basis) return null;

  return (
    <section className="basis-panel card-panel">
      <div className="basis-head">
        <div>
          <div className="section-title">Current Display Basis</div>
          <div className="section-subtitle">
            query={basis.request_date} / run_date={basis.selected_date}
          </div>
        </div>
        <div className={basis.stale_against_inputs ? 'tag tag-danger' : 'tag tag-success'}>
          {basis.stale_against_inputs ? 'RUN OLDER THAN INPUTS' : 'RUN IN SYNC'}
        </div>
      </div>
      <div className="basis-grid">
        <div className="metric-box">
          <div className="metric-label">Run Updated</div>
          <div className="metric-value small">{fmtDateTime(basis.run_updated_at)}</div>
        </div>
        <div className="metric-box">
          <div className="metric-label">Input Max</div>
          <div className="metric-value small">{basis.reference_data_time || '-'}</div>
        </div>
        <div className="metric-box">
          <div className="metric-label">AI Model</div>
          <div className="metric-value small">{basis.llm_model || basis.llm_provider || '-'}</div>
        </div>
        <div className="metric-box">
          <div className="metric-label">AI Calls</div>
          <div className="metric-value small">
            {basis.llm_calls_used} / {basis.overall_ai_top_k}
          </div>
        </div>
      </div>
      {basis.stale_against_inputs ? <div className="warning-box">{basis.stale_reason}</div> : null}
      <div className="basis-source-list">
        {basis.sources.map((source) => (
          <div className="basis-source-item" key={source.label}>
            <span className="basis-source-label">{source.label}</span>
            <span className="basis-source-status">{source.status}</span>
            <span className="basis-source-time">{fmtDateTime(source.updated_at)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

import React from 'react';
import type { BatchTaskItem, RunAllState } from '../../types/api';
import { fmtDateTime, fmtNumber } from '../../app/formatters';

// 이 컴포넌트는 Data Status 화면 카드 목록을 렌더링한다.
interface BatchStatusViewProps {
  loading: boolean;
  tasks: BatchTaskItem[];
  source: string;
  runAll: RunAllState;
  onRefresh: () => void;
  onChangeSource: (source: string) => void;
  onRunTask: (taskId: string) => void;
  onRunAll: () => void;
  onOpenPreview: (taskId: string) => void;
  onOpenLogs: (taskId: string) => void;
}

export function BatchStatusView(props: BatchStatusViewProps) {
  const { loading, tasks, source, runAll, onRefresh, onChangeSource, onRunTask, onRunAll, onOpenPreview, onOpenLogs } = props;
  const skeletonCards = Array.from({ length: 6 }, (_, index) => index);

  return (
    <section>
      <div className="toolbar">
        <div className="toolbar-left">
          <button className="primary-button" onClick={onRunAll} disabled={runAll.running}>
            Run All
          </button>
          <button className="ghost-button" onClick={onRefresh}>
            Refresh Status
          </button>
          <div className="source-toggle" role="radiogroup" aria-label="collector source">
            <button
              className={source === 'naver' ? 'tag tag-success' : 'tag'}
              onClick={() => onChangeSource('naver')}
            >
              Naver
            </button>
            <button
              className={source === 'kiwoom' ? 'tag tag-success' : 'tag'}
              onClick={() => onChangeSource('kiwoom')}
            >
              Kiwoom API
            </button>
          </div>
        </div>
        <div className="toolbar-right">
          <span className={runAll.status === 'OK' ? 'tag tag-success' : runAll.status === 'ERROR' ? 'tag tag-danger' : 'tag'}>
            RunAll: {runAll.status}
          </span>
          {runAll.current_task ? <span className="muted-text">Running: {runAll.current_task}</span> : null}
        </div>
      </div>

      <div className="card-grid">
        {(loading && tasks.length === 0 ? skeletonCards : tasks).map((task, index) => {
          if (typeof task === 'number') {
            return <div key={`skeleton-${index}`} className="card-panel skeleton-card" />;
          }
          const sourceLabel = task.supported_sources.includes('kiwoom') ? task.effective_source.toUpperCase() : 'NAVER';
          return (
            <article className="card-panel batch-card" key={task.id}>
              <div className="batch-head">
                <div>
                  <div className="batch-title">{task.title}</div>
                  <div className="batch-group">{task.group}</div>
                </div>
                <span className={task.status === 'OK' ? 'tag tag-success' : task.status === 'ERROR' ? 'tag tag-danger' : 'tag'}>
                  {task.status}
                </span>
              </div>
              <div className="batch-path">{task.output_target}</div>
              <div className="batch-source-line">Source: {sourceLabel}</div>
              <div className="meta-list">
                <div><span>Updated</span><strong>{fmtDateTime(task.updated_at)}</strong></div>
                <div><span>Last Updated</span><strong>{task.updated_ago}</strong></div>
                <div><span>Records</span><strong>{fmtNumber(task.records)}</strong></div>
                <div><span>Run Date</span><strong>{task.run_date || '-'}</strong></div>
                <div><span>Input Max</span><strong>{task.reference_data_time || '-'}</strong></div>
              </div>
              <div className="button-row">
                <button className="ghost-button" disabled={task.running} onClick={() => onRunTask(task.id)}>Update</button>
                <button className="ghost-button" onClick={() => onOpenPreview(task.id)}>View</button>
                <button className="ghost-button" onClick={() => onOpenLogs(task.id)}>Logs</button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

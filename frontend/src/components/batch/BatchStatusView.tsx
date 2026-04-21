import React from 'react';
import clsx from 'clsx';
import { RefreshCw, Play, Eye, FileText, Loader2 } from 'lucide-react';
import type { BatchTaskItem, RunAllState } from '../../types/api';
import { fmtDateTime, fmtCount } from '../../app/formatters';
import { Badge, type BadgeVariant } from '../ui/Badge';

// Design Ref: Design §4.6 — 배치 상태 그리드 뷰.

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

function statusVariant(status: string): BadgeVariant {
  const s = (status || '').toUpperCase();
  if (s === 'OK' || s === 'SUCCESS') return 'success';
  if (s === 'ERROR' || s === 'FAILED') return 'danger';
  if (s === 'RUNNING') return 'info';
  if (s === 'WARN' || s === 'WARNING') return 'warn';
  return 'neutral';
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] text-text-muted">{label}</span>
      <span className="num text-xs text-text-primary truncate max-w-[65%] text-right">
        {value}
      </span>
    </div>
  );
}

export function BatchStatusView({
  loading,
  tasks,
  source,
  runAll,
  onRefresh,
  onChangeSource,
  onRunTask,
  onRunAll,
  onOpenPreview,
  onOpenLogs,
}: BatchStatusViewProps) {
  const skeletonCount = 6;
  const isSkeletonMode = loading && tasks.length === 0;

  const buttonCls =
    'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

  return (
    <section className="flex flex-col gap-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <button
            onClick={onRunAll}
            disabled={runAll.running}
            className={clsx(buttonCls, 'bg-brand hover:bg-brand-hover border-brand text-white')}
          >
            {runAll.running ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Play size={12} />
            )}
            Run All
          </button>
          <button
            onClick={onRefresh}
            className={clsx(
              buttonCls,
              'border-border bg-surface text-text-primary hover:bg-elevated',
            )}
          >
            <RefreshCw size={12} />
            Refresh
          </button>
          <div
            role="radiogroup"
            aria-label="collector source"
            className="inline-flex items-center rounded-md border border-border-subtle bg-base p-0.5"
          >
            {(['naver', 'kiwoom'] as const).map((key) => (
              <button
                key={key}
                role="radio"
                aria-checked={source === key}
                onClick={() => onChangeSource(key)}
                className={clsx(
                  'px-2.5 py-1 rounded-sm text-xs transition-colors',
                  source === key
                    ? 'bg-elevated text-text-primary font-medium'
                    : 'text-text-secondary hover:text-text-primary',
                )}
              >
                {key === 'naver' ? 'Naver' : 'Kiwoom API'}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-muted">RunAll</span>
          <Badge
            variant={
              runAll.status === 'OK'
                ? 'success'
                : runAll.status === 'ERROR'
                  ? 'danger'
                  : runAll.status === 'RUNNING'
                    ? 'info'
                    : 'neutral'
            }
            size="xs"
          >
            {runAll.status}
          </Badge>
          {runAll.current_task ? (
            <span className="text-text-muted">
              Running: <span className="num text-text-secondary">{runAll.current_task}</span>
            </span>
          ) : null}
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3">
        {isSkeletonMode
          ? Array.from({ length: skeletonCount }).map((_, index) => (
              <div
                key={`skeleton-${index}`}
                className="rounded-md border border-border-subtle bg-surface p-3 h-[180px] animate-pulse"
              />
            ))
          : tasks.map((task) => {
              const sourceLabel = task.supported_sources.includes('kiwoom')
                ? task.effective_source.toUpperCase()
                : 'NAVER';
              const isRunning = task.running || runAll.current_task === task.id;
              return (
                <article
                  key={task.id}
                  className={clsx(
                    'rounded-md border bg-surface p-3 flex flex-col gap-2',
                    isRunning
                      ? 'border-info/40 shadow-[0_0_0_1px_var(--accent-info)]'
                      : 'border-border-subtle',
                  )}
                >
                  <header className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-text-primary truncate">
                        {task.title}
                      </div>
                      <div className="text-[11px] text-text-muted">{task.group}</div>
                    </div>
                    <Badge variant={statusVariant(task.status)} size="xs">
                      {isRunning ? 'RUNNING' : task.status}
                    </Badge>
                  </header>
                  <div className="num text-[11px] text-text-muted truncate" title={task.output_target}>
                    {task.output_target}
                  </div>
                  <div className="text-[11px] text-text-secondary">
                    Source: <span className="text-text-primary">{sourceLabel}</span>
                  </div>
                  <div className="flex flex-col gap-0.5 py-1 border-y border-border-subtle">
                    <MetaRow label="Updated" value={fmtDateTime(task.updated_at)} />
                    <MetaRow label="Ago" value={task.updated_ago} />
                    <MetaRow label="Records" value={fmtCount(task.records)} />
                    <MetaRow label="Run Date" value={task.run_date || '-'} />
                    <MetaRow label="Input Max" value={task.reference_data_time || '-'} />
                  </div>
                  <div className="flex items-center gap-1.5 mt-auto pt-1">
                    <button
                      disabled={isRunning}
                      onClick={() => onRunTask(task.id)}
                      className={clsx(
                        buttonCls,
                        'border-border bg-surface text-text-primary hover:bg-elevated',
                      )}
                    >
                      {isRunning ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Play size={12} />
                      )}
                      Update
                    </button>
                    <button
                      onClick={() => onOpenPreview(task.id)}
                      className={clsx(
                        buttonCls,
                        'border-border-subtle bg-base text-text-secondary hover:bg-elevated hover:text-text-primary',
                      )}
                    >
                      <Eye size={12} />
                      View
                    </button>
                    <button
                      onClick={() => onOpenLogs(task.id)}
                      className={clsx(
                        buttonCls,
                        'border-border-subtle bg-base text-text-secondary hover:bg-elevated hover:text-text-primary',
                      )}
                    >
                      <FileText size={12} />
                      Logs
                    </button>
                  </div>
                </article>
              );
            })}
      </div>

      {runAll.error_task || runAll.error_message ? (
        <div className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {runAll.error_task ? <span className="num">[{runAll.error_task}] </span> : null}
          {runAll.error_message}
        </div>
      ) : null}
    </section>
  );
}

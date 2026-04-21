import React from 'react';
import { BatchStatusView } from '../components/batch/BatchStatusView';
import type { BatchListResponse, BatchLogResponse, PreviewResponse } from '../types/api';
import { Modal } from '../components/common/Modal';

// Design Ref: Design §4.6 — Data Status 화면 + Preview/Logs 모달.

interface DataStatusPageProps {
  loading: boolean;
  data?: BatchListResponse | null;
  source: string;
  previewOpen: boolean;
  preview?: PreviewResponse | null;
  previewTitle: string;
  logOpen: boolean;
  log?: BatchLogResponse | null;
  logTitle: string;
  onRefresh: () => void;
  onChangeSource: (source: string) => void;
  onRunTask: (taskId: string) => void;
  onRunAll: () => void;
  onOpenPreview: (taskId: string) => void;
  onOpenLogs: (taskId: string) => void;
  onClosePreview: () => void;
  onCloseLog: () => void;
}

export function DataStatusPage(props: DataStatusPageProps) {
  const {
    loading,
    data,
    source,
    previewOpen,
    preview,
    previewTitle,
    logOpen,
    log,
    logTitle,
    onRefresh,
    onChangeSource,
    onRunTask,
    onRunAll,
    onOpenPreview,
    onOpenLogs,
    onClosePreview,
    onCloseLog,
  } = props;

  return (
    <>
      <BatchStatusView
        loading={loading}
        tasks={data?.tasks ?? []}
        source={source}
        runAll={data?.run_all ?? { running: false, status: 'IDLE', completed_tasks: [] }}
        onRefresh={onRefresh}
        onChangeSource={onChangeSource}
        onRunTask={onRunTask}
        onRunAll={onRunAll}
        onOpenPreview={onOpenPreview}
        onOpenLogs={onOpenLogs}
      />

      <Modal open={previewOpen} title={previewTitle} onClose={onClosePreview} size="xl">
        {!preview ? (
          <div className="p-6 text-text-muted text-sm">Preview 데이터 없음</div>
        ) : (
          <div className="overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 bg-surface border-b border-border z-10">
                <tr>
                  {preview.columns.map((column) => (
                    <th
                      key={column}
                      className="text-left px-2.5 py-2 text-xs font-medium text-text-secondary uppercase tracking-wide"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, index) => (
                  <tr
                    key={`preview-${index}`}
                    className="border-b border-border-subtle hover:bg-row-hover"
                  >
                    {preview.columns.map((column) => (
                      <td
                        key={`${index}-${column}`}
                        className="num px-2.5 py-1.5 text-text-primary"
                      >
                        {String(row[column] ?? '')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      <Modal open={logOpen} title={logTitle} onClose={onCloseLog} size="lg">
        {!log ? (
          <div className="p-6 text-text-muted text-sm">로그 없음</div>
        ) : (
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-5 gap-2 text-xs">
              <div>
                <div className="text-text-muted">status</div>
                <div className="text-text-primary">{log.status}</div>
              </div>
              <div>
                <div className="text-text-muted">running</div>
                <div className="text-text-primary">{String(log.running)}</div>
              </div>
              <div>
                <div className="text-text-muted">started</div>
                <div className="num text-text-primary truncate">{log.started_at ?? '-'}</div>
              </div>
              <div>
                <div className="text-text-muted">finished</div>
                <div className="num text-text-primary truncate">{log.finished_at ?? '-'}</div>
              </div>
              <div>
                <div className="text-text-muted">exit_code</div>
                <div className="num text-text-primary">{log.exit_code ?? '-'}</div>
              </div>
            </div>
            <details open>
              <summary className="cursor-pointer text-xs font-medium text-text-secondary hover:text-text-primary select-none">
                STDOUT
              </summary>
              <pre className="num mt-2 max-h-[50vh] overflow-auto rounded-md border border-border-subtle bg-base p-3 text-xs text-text-primary whitespace-pre-wrap break-all">
                {log.stdout_tail || '(empty)'}
              </pre>
            </details>
            <details>
              <summary className="cursor-pointer text-xs font-medium text-text-secondary hover:text-text-primary select-none">
                STDERR
              </summary>
              <pre className="num mt-2 max-h-[40vh] overflow-auto rounded-md border border-border-subtle bg-base p-3 text-xs text-danger whitespace-pre-wrap break-all">
                {log.stderr_tail || '(empty)'}
              </pre>
            </details>
          </div>
        )}
      </Modal>
    </>
  );
}

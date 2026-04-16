import React from 'react';
import { BatchStatusView } from '../components/batch/BatchStatusView';
import type { BatchListResponse, BatchLogResponse, PreviewResponse } from '../types/api';
import { Modal } from '../components/common/Modal';

// 이 페이지는 Data Status 화면과 Preview/Logs 모달을 함께 그린다.
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

      <Modal open={previewOpen} title={previewTitle} onClose={onClosePreview}>
        {!preview ? (
          <div className="muted-text">Preview 데이터 없음</div>
        ) : (
          <div className="table-panel compact-table">
            <table className="data-table">
              <thead>
                <tr>
                  {preview.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, index) => (
                  <tr key={`preview-${index}`}>
                    {preview.columns.map((column) => (
                      <td key={`${index}-${column}`}>{String(row[column] ?? '')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Modal>

      <Modal open={logOpen} title={logTitle} onClose={onCloseLog}>
        {!log ? (
          <div className="muted-text">로그 없음</div>
        ) : (
          <pre className="log-box">{[
            `status: ${log.status}`,
            `running: ${log.running}`,
            `started_at: ${log.started_at ?? '-'}`,
            `finished_at: ${log.finished_at ?? '-'}`,
            `exit_code: ${log.exit_code ?? '-'}`,
            '',
            '---- STDOUT ----',
            log.stdout_tail || '',
            '',
            '---- STDERR ----',
            log.stderr_tail || '',
          ].join('\n')}</pre>
        )}
      </Modal>
    </>
  );
}

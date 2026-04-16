// 이 파일은 화면별 API 호출 함수를 한 곳에 모은다.
import { fetchJson } from './client';
import type { BatchListResponse, BatchLogResponse, ClosingBetResponse, DashboardResponse, DateListResponse, PerformanceRefreshResponse, PerformanceResponse, PreviewResponse, TradeHistoryResponse } from '../types/api';

export function getDates() {
  return fetchJson<DateListResponse>('/api/closing-bet/dates');
}

export function getClosingBet(params: URLSearchParams) {
  return fetchJson<ClosingBetResponse>(`/api/closing-bet?${params.toString()}`);
}

export function getPerformance(params: URLSearchParams) {
  return fetchJson<PerformanceResponse>(`/api/performance?${params.toString()}`);
}

export function quickRefreshPerformance(dateFrom: string, dateTo: string) {
  const params = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  return fetchJson<PerformanceRefreshResponse>(`/api/performance/quick-refresh?${params.toString()}`, {
    method: 'POST',
  });
}

export function getBatches() {
  return fetchJson<BatchListResponse>('/api/batches');
}

export function runBatch(taskId: string, source: string) {
  return fetchJson<{ status: string; task_id: string }>(`/api/batches/${taskId}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ source }),
  });
}

export function runAllBatches(source: string) {
  return fetchJson<{ status: string }>('/api/batches/run-all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ source }),
  });
}

export function getBatchPreview(taskId: string, limit = 20) {
  return fetchJson<PreviewResponse>(`/api/batches/${taskId}/preview?limit=${limit}`);
}

export function getBatchLogs(taskId: string) {
  return fetchJson<BatchLogResponse>(`/api/batches/${taskId}/logs`);
}

export function getDashboard(refreshAccount = false, forceRefresh = false) {
  const params = new URLSearchParams();
  if (refreshAccount) {
    params.set('refresh_account', 'true');
  }
  if (forceRefresh) {
    params.set('force_refresh', 'true');
  }
  const query = params.toString();
  return fetchJson<DashboardResponse>(`/api/dashboard${query ? `?${query}` : ''}`);
}

export function getTradeHistory(params: URLSearchParams) {
  return fetchJson<TradeHistoryResponse>(`/api/trade-history?${params.toString()}`);
}

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

// Design Ref: Design §5.7 + §9 Module G — 자동매매 컨트롤 API
export interface LastExtractStatus {
  run_at: string;
  target_date: string;
  actual_data_date: string;
  status: 'OK' | 'STALE_SKIP' | 'NO_CANDIDATES' | 'DB_ERROR';
  picked_count: number;
  message: string;
}

export interface ControlStatusResponse {
  kill_switch_enabled: boolean;
  paper_mode: boolean;
  trading_mode: 'real' | 'mock';
  scheduler_alive?: boolean;
  jobs: Array<{ name: string; enabled: boolean }>;
  last_extract_status?: LastExtractStatus | null;
  state_dir: string;
}

export interface Top2Candidate {
  rank: number;
  stock_code: string;
  stock_name: string;
  sector: string | null;
  score_total: number;
  quality_grade: string;
  quality_label: string;
  base_grade: string;
  final_grade: string;
  change_pct: number;
  trading_value: number;
  entry_price_hint: number;
  nxt_eligible: boolean;
  recommended_window: string | null;
  created_at?: string | null;
}

export interface Top2Response {
  date: string;
  created_at: string | null;
  candidates: Top2Candidate[];
  error?: string;
}

export interface BriefingItem {
  brief_time: string;
  stock_code: string;
  news_status: string;
  liquidity_status: string;
  liquidity_score: number;
  divergence_pct: number | null;
  divergence_warn: boolean;
  us_es_chg_pct: number;
  us_nq_chg_pct: number;
  us_risk_off: boolean;
  action: string;
}

export interface BriefingResponse {
  date: string;
  briefings: BriefingItem[];
  error?: string;
}

export interface AutoOrderItem {
  order_id: string;
  stock_code: string;
  side: 'BUY' | 'SELL';
  tranche: string;
  venue: string;
  order_type: string;
  price: number;
  qty: number;
  status: string;
  filled_qty: number;
  filled_avg_price: number;
  requested_at: string | null;
  filled_at: string | null;
  paper_mode: boolean;
  error_msg: string | null;
}

export interface OrderListResponse {
  date: string;
  orders: AutoOrderItem[];
  error?: string;
}

export function getControlStatus() {
  return fetchJson<ControlStatusResponse>('/api/controls/status');
}

export function setKillSwitch(enabled: boolean) {
  return fetchJson<ControlStatusResponse>('/api/controls/killswitch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ enabled }),
  });
}

export function setPaperMode(enabled: boolean) {
  return fetchJson<ControlStatusResponse>('/api/controls/paper', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ enabled }),
  });
}

export function setTradingMode(mode: 'real' | 'mock') {
  return fetchJson<ControlStatusResponse>('/api/controls/trading-mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ mode }),
  });
}

export function toggleJob(jobName: string, enabled: boolean) {
  return fetchJson<{ job_name: string; enabled: boolean }>(`/api/controls/job/${jobName}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json;charset=UTF-8' },
    body: JSON.stringify({ enabled }),
  });
}

export function getTop2Candidates() {
  return fetchJson<Top2Response>('/api/controls/candidates/top2');
}

export function getLatestBriefing() {
  return fetchJson<BriefingResponse>('/api/controls/briefing');
}

export function getTodayOrders() {
  return fetchJson<OrderListResponse>('/api/controls/orders/today');
}

// ─── 실행 히스토리 ─────────────────────────────────
export interface HistoryListItem {
  history_date: string;
  title: string;
  summary: string;
  event_count: number;
  version: number;
  updated_at: string | null;
}

export interface HistoryListResponse {
  items: HistoryListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  error?: string;
}

export interface HistoryEvent {
  ts: string;
  event_type: string;
  summary: string;
  details?: Record<string, unknown>;
}

export interface HistoryDetail extends HistoryListItem {
  content: string;
  events: HistoryEvent[];
}

export function getHistoryList(page = 1, pageSize = 20) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return fetchJson<HistoryListResponse>(`/api/history/list?${params.toString()}`);
}

export function getHistoryDetail(date: string) {
  return fetchJson<HistoryDetail>(`/api/history/${date}`);
}

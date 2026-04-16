// 이 파일은 프론트에서 공통으로 사용하는 API 타입을 정의한다.
export type ViewKey = 'dashboard' | 'data_status' | 'closing' | 'performance';

export interface BasisSourceItem {
  label: string;
  status: string;
  updated_at?: string | null;
  updated_ago: string;
  max_data_time?: string | null;
  records: number;
}

export interface BasisPayload {
  request_date: string;
  selected_date: string;
  run_updated_at?: string | null;
  run_updated_ago: string;
  reference_data_time?: string | null;
  reference_data_ago: string;
  stale_against_inputs: boolean;
  stale_reason: string;
  llm_provider: string;
  llm_model: string;
  llm_calls_used: number;
  overall_ai_top_k: number;
  sources: BasisSourceItem[];
}

export interface ClosingBetItem {
  rank: number;
  global_rank: number;
  ticker: string;
  name: string;
  market: string;
  grade: string;
  base_grade: string;
  score_total: number;
  score_max: number;
  scores: Record<string, number>;
  change_pct: number;
  trading_value: number;
  entry_price: number;
  current_price: number;
  target_price: number;
  stop_price: number;
  ai_analysis: string;
  analysis_status: string;
  analysis_status_label: string;
  ai_opinion: string;
  decision_status: string;
  decision_label: string;
  ai_evidence: string[];
  ai_breakdown: Record<string, unknown>;
  references: Array<Record<string, unknown>>;
  themes: string[];
  foreign_1d: number;
  inst_1d: number;
  foreign_5d: number;
  inst_5d: number;
  market_context: Record<string, unknown>;
  program_context: Record<string, unknown>;
  stock_program_context: Record<string, unknown>;
  external_market_context: Record<string, unknown>;
  market_policy: Record<string, unknown>;
  minute_pattern_label: string;
  market_status_label: string;
  external_market_status_label: string;
  chart_url: string;
}

export interface PaginationPayload {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ClosingBetResponse {
  date: string;
  is_today: boolean;
  status: string;
  candidates_count: number;
  signals_count: number;
  buyable_signals_count: number;
  featured_count: number;
  grade_counts: Record<string, number>;
  featured_items: ClosingBetItem[];
  items: ClosingBetItem[];
  pagination: PaginationPayload;
  filters: Record<string, string>;
  basis: BasisPayload;
}

export interface DateListResponse {
  dates: string[];
  latest?: string | null;
}

export interface PerformanceSummary {
  total_signals: number;
  win_rate: number;
  wins: number;
  losses: number;
  open: number;
  avg_roi: number;
  total_roi: number;
  profit_factor: number;
  avg_days: number;
}

export interface PerformanceComparison {
  better_slot: string;
  win_rate_08: number;
  win_rate_09: number;
  edge_pct: number;
}

export interface PerformanceRefreshResponse {
  status: string;
  tracked_count: number;
  refreshed_08: number;
  refreshed_09: number;
  skipped_08: number;
  skipped_09: number;
  message: string;
}

export interface GradeSummaryItem {
  grade: string;
  count: number;
  win_rate: number;
  avg_roi: number;
  wl: string;
  win_rate_08: number;
  avg_roi_08: number;
  wl_08: string;
  win_rate_09: number;
  avg_roi_09: number;
  wl_09: string;
}

export interface PerformanceTradeItem {
  key: number;
  date: string;
  buy_date?: string | null;
  grade: string;
  name: string;
  ticker: string;
  entry: number;
  outcome: string;
  roi: number;
  max_high: number;
  price_trail: string;
  days: number;
  score: number;
  themes: string[];
  eval_date?: string | null;
  eval_08_price?: number | null;
  eval_08_time?: string | null;
  eval_08_venue?: string | null;
  outcome_08: string;
  roi_08?: number | null;
  eval_09_price?: number | null;
  eval_09_time?: string | null;
  eval_09_venue?: string | null;
  outcome_09: string;
  roi_09?: number | null;
}

export interface PerformanceResponse {
  date: string;
  is_today: boolean;
  summary: PerformanceSummary;
  summary_08: PerformanceSummary;
  summary_09: PerformanceSummary;
  comparison: PerformanceComparison;
  grade_summary: GradeSummaryItem[];
  distribution: Record<string, number>;
  trades: PerformanceTradeItem[];
  pagination: PaginationPayload;
  basis: BasisPayload;
}

export interface BatchTaskItem {
  id: string;
  title: string;
  group: string;
  output_target: string;
  status: string;
  running: boolean;
  updated_at?: string | null;
  updated_ago: string;
  records: number;
  run_date?: string | null;
  reference_data_time?: string | null;
  source: string;
  supported_sources: string[];
  effective_source: string;
  started_at?: string | null;
  finished_at?: string | null;
  exit_code?: number | null;
}

export interface RunAllState {
  running: boolean;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  current_task?: string | null;
  completed_tasks: string[];
  error_task?: string | null;
  error_message?: string | null;
}

export interface BatchListResponse {
  tasks: BatchTaskItem[];
  run_all: RunAllState;
}

export interface PreviewResponse {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}

export interface BatchLogResponse {
  task_id: string;
  status: string;
  running: boolean;
  started_at?: string | null;
  finished_at?: string | null;
  exit_code?: number | null;
  stdout_tail: string;
  stderr_tail: string;
}

export interface DashboardMarketItem {
  market: string;
  market_label: string;
  market_status: string;
  market_status_label: string;
  index_value: number;
  change_pct: number;
  rise_count: number;
  steady_count: number;
  fall_count: number;
  upper_count: number;
  lower_count: number;
  total_net: number;
  non_arbitrage_net: number;
  snapshot_time?: string | null;
}

export interface DashboardAccountPayload {
  available: boolean;
  account_no?: string | null;
  snapshot_time?: string | null;
  venue?: string | null;
  total_purchase_amt: number;
  total_eval_amt: number;
  total_eval_profit: number;
  total_profit_rate: number;
  estimated_assets: number;
  holdings_count: number;
  realized_profit: number;
  unfilled_count: number;
  total_unfilled_qty: number;
  avg_fill_latency_ms: number;
  est_slippage_bps: number;
  note: string;
}

export interface DashboardPickPayload {
  ticker: string;
  name: string;
  market: string;
  sector: string;
  grade: string;
  base_grade: string;
  decision_status: string;
  decision_label: string;
  score_total: number;
  trading_value: number;
  change_pct: number;
  current_price: number;
  entry_price: number;
  target_price: number;
  stop_price: number;
  foreign_1d: number;
  inst_1d: number;
  foreign_5d: number;
  inst_5d: number;
  venue?: string | null;
  ai_summary: string;
  ai_evidence: string[];
  report_title: string;
  report_body: string;
  key_points: string[];
  references: Array<Record<string, unknown>>;
  intraday: Record<string, unknown>;
  minute_pattern_label: string;
}

export interface DashboardResponse {
  date: string;
  market_summary: string;
  markets: DashboardMarketItem[];
  picks: DashboardPickPayload[];
  account: DashboardAccountPayload;
}

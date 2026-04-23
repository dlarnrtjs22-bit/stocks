import React, { useCallback, useEffect, useState } from 'react';
import { AlertCircle, Play, Pause, Shield, TestTube2, Target, RefreshCw, Clock, TrendingUp, TrendingDown, AlertTriangle, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import {
  getControlStatus, setKillSwitch, setPaperMode, setTradingMode, toggleJob,
  getTop2Candidates, getLatestBriefing, getTodayOrders,
  getHistoryList, getHistoryDetail,
  type ControlStatusResponse, type Top2Response, type BriefingResponse, type OrderListResponse,
  type HistoryListResponse, type HistoryDetail,
} from '../api/endpoints';
import { Panel } from '../components/ui/Panel';
import { Badge, type BadgeVariant } from '../components/ui/Badge';
import { Num } from '../components/ui/Num';

// Design Ref: Design §5.7 + §9 Module G — 자동매매 전체 컨트롤
// Plan §9: 실시간 on/off UI, 실전/모의 선택

const REFRESH_INTERVAL_MS = 10_000;

function ToggleRow({
  label,
  enabled,
  onToggle,
  variant = 'info',
  description,
  confirmMessage,
}: {
  label: string;
  enabled: boolean;
  onToggle: (enabled: boolean) => Promise<void>;
  variant?: 'info' | 'danger' | 'warn' | 'success';
  description?: string;
  confirmMessage?: string;
}) {
  const [busy, setBusy] = useState(false);
  const handleClick = async () => {
    if (busy) return;
    const next = !enabled;
    if (confirmMessage && !window.confirm(`${confirmMessage}\n\n${next ? 'ON' : 'OFF'}으로 전환할까요?`)) {
      return;
    }
    setBusy(true);
    try {
      await onToggle(next);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-md border border-border-subtle bg-surface">
      <div className="flex flex-col min-w-0">
        <span className="text-sm font-medium text-text-primary">{label}</span>
        {description ? <span className="text-[11px] text-text-muted">{description}</span> : null}
      </div>
      <button
        onClick={handleClick}
        disabled={busy}
        className={clsx(
          'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border text-xs font-semibold transition-colors',
          enabled
            ? 'bg-success/15 border-success/40 text-success hover:bg-success/20'
            : 'bg-elevated border-border text-text-secondary hover:bg-base',
          busy && 'opacity-50 cursor-wait',
        )}
      >
        {enabled ? <Play size={12} /> : <Pause size={12} />}
        {enabled ? 'ON' : 'OFF'}
      </button>
    </div>
  );
}

function ModeSwitchCard({
  status,
  onSetTradingMode,
}: {
  status: ControlStatusResponse;
  onSetTradingMode: (mode: 'real' | 'mock') => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const handle = async (mode: 'real' | 'mock') => {
    if (mode === status.trading_mode) return;
    const warn = mode === 'real'
      ? '실전투자 모드로 전환합니다.\n실제 돈으로 주문이 나갑니다.\n계속할까요?'
      : '모의투자 모드로 전환합니다.\n(mockapi.kiwoom.com 사용)';
    if (!window.confirm(warn)) return;
    setBusy(true);
    try {
      await onSetTradingMode(mode);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="거래 모드" subtitle="실전투자 ↔ 모의투자 선택 (키움 API URL 스위치)" tone="default">
      <div className="flex gap-2">
        <button
          onClick={() => handle('mock')}
          disabled={busy}
          className={clsx(
            'flex-1 px-4 py-3 rounded-md border-2 text-sm font-semibold transition',
            status.trading_mode === 'mock'
              ? 'bg-info/15 border-info text-info'
              : 'bg-surface border-border-subtle text-text-secondary hover:border-border',
          )}
        >
          <TestTube2 size={14} className="inline mr-1.5" />
          모의투자 (MOCK)
        </button>
        <button
          onClick={() => handle('real')}
          disabled={busy}
          className={clsx(
            'flex-1 px-4 py-3 rounded-md border-2 text-sm font-semibold transition',
            status.trading_mode === 'real'
              ? 'bg-danger/15 border-danger text-danger'
              : 'bg-surface border-border-subtle text-text-secondary hover:border-border',
          )}
        >
          <Target size={14} className="inline mr-1.5" />
          실전투자 (REAL)
        </button>
      </div>
      <div className="mt-2 text-[11px] text-text-muted">
        현재: <span className="text-text-primary font-mono">{status.trading_mode === 'mock' ? 'mockapi.kiwoom.com' : 'api.kiwoom.com'}</span>
      </div>
    </Panel>
  );
}

function Top2Card({ top2 }: { top2: Top2Response | null }) {
  if (!top2 || !top2.candidates?.length) {
    return (
      <Panel title="오늘의 Top 2 후보" subtitle="15:30 자동 추출 결과" tone="default">
        <div className="text-xs text-text-muted py-4">후보 없음 (15:30 배치 대기 중 또는 NXT 가능 매수 후보 부재)</div>
      </Panel>
    );
  }
  return (
    <Panel
      title="오늘의 Top 2 후보"
      subtitle={`15:30 자동 추출 · ${top2.created_at ? new Date(top2.created_at).toLocaleTimeString('ko') : ''}`}
      tone="default"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {top2.candidates.map((c) => (
          <div
            key={`${c.rank}-${c.stock_code}`}
            className="rounded-md border border-border-subtle bg-surface p-3 flex flex-col gap-1.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <Badge variant={c.rank === 1 ? 'up' : 'info'} size="xs">#{c.rank}</Badge>
                  <Badge variant={c.nxt_eligible ? 'up' : 'neutral'} size="xs">
                    {c.nxt_eligible ? 'NXT ✓' : 'KRX only'}
                  </Badge>
                </div>
                <div className="mt-1 text-sm font-semibold text-text-primary truncate">{c.stock_name}</div>
                <div className="num text-[11px] text-text-muted">
                  {c.stock_code} · {c.sector || 'General'}
                </div>
              </div>
              <div className="text-right">
                <Badge variant={c.final_grade === 'S' ? 'up' : c.final_grade === 'A' ? 'info' : 'neutral'}>
                  {c.final_grade}
                </Badge>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-1 text-[11px]">
              <div>
                <div className="text-text-muted">점수</div>
                <div className="text-text-primary num">{c.score_total}</div>
              </div>
              <div>
                <div className="text-text-muted">등락</div>
                <Num value={c.change_pct} format="signed-percent" showArrow />
              </div>
              <div>
                <div className="text-text-muted">진입</div>
                <Num value={c.entry_price_hint} format="price" />
              </div>
            </div>
            <div className="text-[11px] text-text-secondary mt-0.5">
              매수 시점: <span className="num text-text-primary">{c.recommended_window || '-'}</span>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function BriefingCard({ briefing }: { briefing: BriefingResponse | null }) {
  if (!briefing || !briefing.briefings?.length) {
    return null;
  }
  // 가장 최근 브리핑 + 각 종목 최신 1개만
  const latestByStock = new Map<string, typeof briefing.briefings[number]>();
  for (const b of briefing.briefings) {
    const prev = latestByStock.get(b.stock_code);
    if (!prev || new Date(b.brief_time).getTime() > new Date(prev.brief_time).getTime()) {
      latestByStock.set(b.stock_code, b);
    }
  }
  const latest = Array.from(latestByStock.values());
  const esPct = latest[0]?.us_es_chg_pct ?? 0;
  const nqPct = latest[0]?.us_nq_chg_pct ?? 0;
  const usRiskOff = latest[0]?.us_risk_off ?? false;
  return (
    <Panel title="19:30 장후 브리핑" subtitle="4축 가드: 뉴스/유동성/가격괴리/미국선물" tone="default">
      <div className="flex items-center gap-3 mb-2 px-2 py-1.5 rounded-md bg-surface border border-border-subtle">
        <span className="text-[11px] text-text-muted">미국 선물:</span>
        <div className={clsx('flex items-center gap-1 text-xs', esPct >= 0 ? 'text-up' : 'text-down')}>
          {esPct >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          ES {esPct >= 0 ? '+' : ''}{esPct.toFixed(2)}%
        </div>
        <div className={clsx('flex items-center gap-1 text-xs', nqPct >= 0 ? 'text-up' : 'text-down')}>
          NQ {nqPct >= 0 ? '+' : ''}{nqPct.toFixed(2)}%
        </div>
        {usRiskOff ? (
          <Badge variant="danger" size="xs">
            <AlertTriangle size={10} className="inline mr-0.5" />
            US RISK OFF
          </Badge>
        ) : null}
      </div>
      <div className="flex flex-col gap-1.5">
        {latest.map((b) => (
          <div key={b.stock_code} className="flex items-center gap-2 text-[11px] px-2 py-1.5 rounded-md border border-border-subtle bg-surface">
            <span className="num text-text-primary font-medium min-w-[60px]">{b.stock_code}</span>
            <Badge variant={b.news_status === 'DETERIORATED' ? 'danger' : 'neutral'} size="xs">
              뉴스 {b.news_status}
            </Badge>
            <Badge variant={b.liquidity_status === 'THIN' ? 'warn' : b.liquidity_status === 'OK' ? 'success' : 'neutral'} size="xs">
              유동 {b.liquidity_status}
            </Badge>
            {b.divergence_pct !== null ? (
              <Badge variant={b.divergence_warn ? 'warn' : 'neutral'} size="xs">
                괴리 {b.divergence_pct.toFixed(2)}%
              </Badge>
            ) : null}
            <ChevronRight size={10} className="text-text-muted" />
            <Badge variant={
              b.action === 'DROP' ? 'danger' :
              b.action === 'QTY_HALF' ? 'warn' :
              b.action === 'REPLACE' ? 'info' : 'success'
            } size="xs">
              {b.action}
            </Badge>
            <span className="ml-auto text-text-muted">{new Date(b.brief_time).toLocaleTimeString('ko', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function OrdersCard({ orders }: { orders: OrderListResponse | null }) {
  if (!orders || !orders.orders?.length) {
    return (
      <Panel title="오늘 자동주문 이력" subtitle="auto_orders" tone="default">
        <div className="text-xs text-text-muted py-2">주문 내역 없음</div>
      </Panel>
    );
  }
  return (
    <Panel title="오늘 자동주문 이력" subtitle={`총 ${orders.orders.length}건`} tone="default">
      <div className="flex flex-col gap-1 max-h-[300px] overflow-y-auto">
        {orders.orders.map((o) => (
          <div
            key={o.order_id}
            className={clsx(
              'grid grid-cols-[50px_90px_60px_50px_70px_80px_70px_auto] gap-2 items-center text-[11px] px-2 py-1.5 rounded border border-border-subtle',
              o.paper_mode ? 'bg-info/5' : 'bg-surface',
            )}
          >
            <Badge variant={o.side === 'BUY' ? 'up' : 'down'} size="xs">{o.side}</Badge>
            <span className="num text-text-primary">{o.stock_code}</span>
            <span className="text-text-muted">{o.tranche}</span>
            <span className="text-text-muted">{o.venue}</span>
            <span className="text-text-muted">{o.order_type}</span>
            <span className="num text-text-primary">{o.price.toLocaleString()}</span>
            <span className="num text-text-primary">{o.qty}</span>
            <div className="flex items-center gap-1">
              <Badge
                variant={
                  o.status === 'FILLED' ? 'success' :
                  o.status === 'FAILED' || o.status === 'CANCELLED' ? 'danger' :
                  o.status === 'PARTIAL' ? 'warn' : 'info'
                }
                size="xs"
              >
                {o.status}
              </Badge>
              {o.paper_mode && <Badge variant="info" size="xs">PAPER</Badge>}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function HistoryBoard() {
  const [list, setList] = useState<HistoryListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [expandedDate, setExpandedDate] = useState<string | null>(null);
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setListLoading(true);
    try {
      const r = await getHistoryList(page, pageSize);
      setList(r);
      setListError(r.error ?? null);
    } catch (e) {
      setListError(String(e));
    } finally {
      setListLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => {
    const t = setInterval(loadList, REFRESH_INTERVAL_MS);
    return () => clearInterval(t);
  }, [loadList]);

  const toggleDetail = async (date: string) => {
    if (expandedDate === date) {
      setExpandedDate(null);
      setDetail(null);
      return;
    }
    setExpandedDate(date);
    setDetailLoading(true);
    try {
      const d = await getHistoryDetail(date);
      setDetail(d);
    } catch (e) {
      setDetail(null);
      setListError(String(e));
    } finally {
      setDetailLoading(false);
    }
  };

  const total = list?.total ?? 0;
  const totalPages = list?.total_pages ?? 0;

  return (
    <Panel
      title="실행 히스토리"
      subtitle={total > 0 ? `총 ${total}일 · page ${page}/${totalPages}` : 'daily_execution_history'}
      tone="default"
    >
      {listError ? (
        <div className="text-xs text-danger mb-2 flex items-center gap-1">
          <AlertCircle size={12} /> {listError}
        </div>
      ) : null}
      {!list || list.items.length === 0 ? (
        <div className="text-xs text-text-muted py-2">
          {listLoading ? '로딩 중…' : '아직 기록된 히스토리가 없습니다.'}
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {list.items.map((it) => {
            const isExpanded = expandedDate === it.history_date;
            return (
              <div key={it.history_date} className="rounded-md border border-border-subtle bg-surface">
                <button
                  onClick={() => toggleDetail(it.history_date)}
                  className={clsx(
                    'w-full flex items-start gap-3 px-3 py-2 text-left transition-colors hover:bg-elevated',
                    isExpanded && 'bg-elevated',
                  )}
                >
                  <ChevronRight
                    size={14}
                    className={clsx('mt-0.5 text-text-muted transition-transform shrink-0', isExpanded && 'rotate-90')}
                  />
                  <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                      <span>{it.title}</span>
                      <Badge variant="neutral" size="xs">{it.event_count} events</Badge>
                      <Badge variant="info" size="xs">v{it.version}</Badge>
                    </div>
                    <div className="text-[11px] text-text-muted truncate">{it.summary || '(요약 없음)'}</div>
                    <div className="text-[10px] text-text-muted">
                      업데이트: {it.updated_at ? new Date(it.updated_at).toLocaleString('ko') : '—'}
                    </div>
                  </div>
                </button>
                {isExpanded ? (
                  <div className="border-t border-border-subtle px-3 py-2.5 bg-base">
                    {detailLoading ? (
                      <div className="text-xs text-text-muted">로딩 중…</div>
                    ) : detail && detail.history_date === it.history_date ? (
                      <>
                        <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-text-primary font-mono max-h-[400px] overflow-y-auto">
                          {detail.content || '(본문 없음)'}
                        </pre>
                        {detail.events?.length ? (
                          <details className="mt-2">
                            <summary className="text-[10px] text-text-muted cursor-pointer hover:text-text-secondary">
                              원본 이벤트 JSON ({detail.events.length}건)
                            </summary>
                            <pre className="mt-1 p-2 rounded bg-elevated text-[10px] text-text-muted max-h-[260px] overflow-y-auto whitespace-pre-wrap">
                              {JSON.stringify(detail.events, null, 2)}
                            </pre>
                          </details>
                        ) : null}
                      </>
                    ) : (
                      <div className="text-xs text-text-muted">본문 로드 실패</div>
                    )}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
      {totalPages > 1 ? (
        <div className="flex items-center justify-center gap-2 mt-3 text-xs">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-2 py-1 rounded border border-border-subtle bg-surface hover:bg-elevated disabled:opacity-40 disabled:cursor-not-allowed"
          >
            이전
          </button>
          <span className="text-text-muted num">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="px-2 py-1 rounded border border-border-subtle bg-surface hover:bg-elevated disabled:opacity-40 disabled:cursor-not-allowed"
          >
            다음
          </button>
        </div>
      ) : null}
    </Panel>
  );
}

interface ControlPageProps {
  loading: boolean;
}

export function ControlPage({ loading }: ControlPageProps) {
  const [status, setStatus] = useState<ControlStatusResponse | null>(null);
  const [top2, setTop2] = useState<Top2Response | null>(null);
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [orders, setOrders] = useState<OrderListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [s, t, b, o] = await Promise.all([
        getControlStatus(),
        getTop2Candidates(),
        getLatestBriefing(),
        getTodayOrders(),
      ]);
      setStatus(s);
      setTop2(t);
      setBriefing(b);
      setOrders(o);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  // 부분 응답 방어: 항상 refresh()로 전체 status 다시 로드
  const handleKillSwitch = async (enabled: boolean) => {
    await setKillSwitch(enabled);
    await refresh();
  };
  const handlePaperMode = async (enabled: boolean) => {
    await setPaperMode(enabled);
    await refresh();
  };
  const handleTradingMode = async (mode: 'real' | 'mock') => {
    await setTradingMode(mode);
    await refresh();
  };
  const handleJobToggle = async (jobName: string, enabled: boolean) => {
    await toggleJob(jobName, enabled);
    await refresh();
  };

  if (loading && !status) {
    return <Panel tone="default"><div className="text-sm text-text-muted">로딩 중...</div></Panel>;
  }
  if (error && !status) {
    return (
      <Panel tone="default">
        <div className="text-sm text-danger flex items-center gap-2">
          <AlertCircle size={14} /> {error}
        </div>
      </Panel>
    );
  }
  if (!status) return null;

  return (
    <div className="flex flex-col gap-3">
      {/* Extract STALE 경고 배너 (오늘 run 없는데 extract 시도됨) */}
      {status.last_extract_status?.status === 'STALE_SKIP' ? (
        <div className="rounded-md border-2 border-danger bg-danger/10 p-3 text-sm text-danger flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div className="flex flex-col gap-0.5">
            <span className="font-semibold">15:30 추출 스킵됨 — 오늘 Run All 결과 없음</span>
            <span className="text-xs">
              target: {status.last_extract_status.target_date} / 실제 데이터:{' '}
              <span className="num">{status.last_extract_status.actual_data_date}</span>
              {' · '}
              15:10 배치가 아직 완료 안됐거나 실패. Data Status에서 Run All 수동 실행 → 그 뒤 extract 수동 트리거 필요
            </span>
          </div>
        </div>
      ) : status.last_extract_status?.status === 'DB_ERROR' ? (
        <div className="rounded-md border-2 border-danger bg-danger/10 p-3 text-sm text-danger flex items-start gap-2">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span className="font-semibold">Extract DB 저장 실패:</span>
          <span className="text-xs">{status.last_extract_status.message}</span>
        </div>
      ) : null}

      {/* Scheduler 상태 배너 */}
      {status.scheduler_alive === false ? (
        <div className="rounded-md border-2 border-warn bg-warn/10 p-3 text-sm text-warn flex items-center gap-2">
          <AlertCircle size={16} />
          <span className="font-semibold">Scheduler 쓰레드 비활성</span>
          <span className="text-xs">— 백엔드 내장 스케줄러가 떠있지 않습니다. STOCKS_SCHEDULER_ENABLED=1 로 재시작하세요.</span>
        </div>
      ) : status.scheduler_alive === true ? (
        <div className="rounded-md border border-success/30 bg-success/5 px-3 py-1.5 text-[11px] text-success flex items-center gap-2">
          <Play size={12} />
          <span>Scheduler 쓰레드 활성 — 백엔드와 함께 상주 중 (별도 서비스 설치 불필요)</span>
        </div>
      ) : null}

      {/* 경고 배너 */}
      {status.kill_switch_enabled && status.trading_mode === 'real' && !status.paper_mode ? (
        <div className="rounded-md border-2 border-danger bg-danger/10 p-3 text-sm text-danger flex items-center gap-2">
          <AlertTriangle size={16} />
          <span className="font-semibold">실전투자 자동매매 활성화 중</span>
          <span className="text-xs">— 실제 돈으로 주문이 나갑니다. 중단하려면 Kill Switch OFF.</span>
        </div>
      ) : null}

      {/* 상단: 주요 토글 3개 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="자동매매 스위치" subtitle="전체 on/off 및 모드" tone="default">
          <div className="flex flex-col gap-2">
            <ToggleRow
              label="Kill Switch (자동매매 활성화)"
              enabled={status.kill_switch_enabled}
              onToggle={handleKillSwitch}
              description="OFF 시 모든 주문이 즉시 차단됩니다 (비상 정지)"
              confirmMessage={status.kill_switch_enabled ? '자동매매를 중단합니다.' : '자동매매를 활성화합니다.\n체크리스트를 확인했나요?'}
            />
            <ToggleRow
              label="Paper Mode (모의 주문)"
              enabled={status.paper_mode}
              onToggle={handlePaperMode}
              description="ON 시 실제 주문 대신 로그만 기록 (검증용)"
            />
          </div>
        </Panel>

        <ModeSwitchCard status={status} onSetTradingMode={handleTradingMode} />
      </div>

      {/* 개별 Job 스위치 */}
      <Panel title="개별 Job 스케줄" subtitle="각 자동 작업 on/off" tone="default">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {(status.jobs ?? []).map((job) => {
            const label = {
              'batches-run-all': '15:10 기존 배치 전체 실행 (LLM 포함, ~3-5분)',
              'extract': '15:30 Top 2 후보 추출 (LLM skip, 즉시)',
              'briefing-1930': '19:30 장후 브리핑 (2종목 LLM 재평가)',
              'briefing-1940': '19:40 재평가',
              'buy': '19:50~19:58 자동매수 (40/30/30%)',
              'sell': '08:00~ 자동매도 스케줄',
              'reconcile': '09:10 일일 P/L 집계',
              'refresh-nxt': '월 06:00 NXT 종목 갱신',
            }[job.name] ?? job.name;
            return (
              <ToggleRow
                key={job.name}
                label={label}
                enabled={job.enabled}
                onToggle={(en) => handleJobToggle(job.name, en)}
              />
            );
          })}
        </div>
      </Panel>

      {/* Top 2 + 브리핑 + 주문 + 실행 히스토리 */}
      <Top2Card top2={top2} />
      {briefing && briefing.briefings && briefing.briefings.length > 0 ? <BriefingCard briefing={briefing} /> : null}
      <OrdersCard orders={orders} />
      <HistoryBoard />

      {/* 새로고침 */}
      <div className="text-[10px] text-text-muted text-right flex items-center justify-end gap-1">
        {refreshing ? <RefreshCw size={10} className="animate-spin" /> : <Clock size={10} />}
        <span>{REFRESH_INTERVAL_MS / 1000}초마다 자동 새로고침 · state: {status.state_dir}</span>
      </div>
    </div>
  );
}

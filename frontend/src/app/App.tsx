import React, { useEffect, useMemo, useState } from 'react';
import { getBatchLogs, getBatchPreview, getBatches, getClosingBet, getDashboard, getDates, getPerformance, getTradeHistory, quickRefreshPerformance, runAllBatches, runBatch } from '../api/endpoints';
import { AppShell } from '../components/layout/AppShell';
import { DashboardPage } from '../pages/DashboardPage';
import { DataStatusPage } from '../pages/DataStatusPage';
import { ClosingBetPage } from '../pages/ClosingBetPage';
import { PerformancePage } from '../pages/PerformancePage';
import { TradeHistoryPage } from '../pages/TradeHistoryPage';
import type {
  BatchListResponse,
  BatchLogResponse,
  ClosingBetResponse,
  DashboardResponse,
  DateListResponse,
  PerformanceRefreshResponse,
  PerformanceResponse,
  PreviewResponse,
  TradeHistoryResponse,
  ViewKey,
} from '../types/api';

function formatInputDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function defaultRange() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - 6);
  return {
    from: formatInputDate(start),
    to: formatInputDate(end),
  };
}

function autoRefreshMs(value: string) {
  if (value === '30S') return 30_000;
  if (value === '1M') return 60_000;
  if (value === '5M') return 300_000;
  if (value === '10M') return 600_000;
  return 0;
}

export function App() {
  const initialRange = defaultRange();
  const [view, setView] = useState<ViewKey>('dashboard');
  const [batchSource, setBatchSource] = useState('naver');
  const [dates, setDates] = useState<DateListResponse>({ dates: [], latest: null });
  const [selectedDate, setSelectedDate] = useState('latest');
  const [tradeDateFrom, setTradeDateFrom] = useState(initialRange.from);
  const [tradeDateTo, setTradeDateTo] = useState(initialRange.to);
  const [performanceDateFrom, setPerformanceDateFrom] = useState(initialRange.from);
  const [performanceDateTo, setPerformanceDateTo] = useState(initialRange.to);
  const [gradeFilter, setGradeFilter] = useState('ALL');
  const [tradeSideFilter, setTradeSideFilter] = useState('ALL');
  const [tradeStatusFilter, setTradeStatusFilter] = useState('ALL');
  const [performanceOutcome, setPerformanceOutcome] = useState('ALL');
  const [closingPage, setClosingPage] = useState(1);
  const [performancePage, setPerformancePage] = useState(1);
  const [closingQuery, setClosingQuery] = useState('');
  const [tradeQuery, setTradeQuery] = useState('');
  const [performanceQuery, setPerformanceQuery] = useState('');
  const [tradeAutoRefresh, setTradeAutoRefresh] = useState('MANUAL');

  const [statusLoading, setStatusLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [batchData, setBatchData] = useState<BatchListResponse | null>(null);
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [tradeHistoryData, setTradeHistoryData] = useState<TradeHistoryResponse | null>(null);
  const [closingData, setClosingData] = useState<ClosingBetResponse | null>(null);
  const [performanceData, setPerformanceData] = useState<PerformanceResponse | null>(null);
  const [performanceRefreshInfo, setPerformanceRefreshInfo] = useState<PerformanceRefreshResponse | null>(null);
  const [dashboardRefreshing, setDashboardRefreshing] = useState(false);
  const [tradeHistoryRefreshing, setTradeHistoryRefreshing] = useState(false);
  const [performanceRefreshing, setPerformanceRefreshing] = useState(false);
  const [performanceQuickRefreshing, setPerformanceQuickRefreshing] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewTitle, setPreviewTitle] = useState('Preview');
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [logOpen, setLogOpen] = useState(false);
  const [logTitle, setLogTitle] = useState('Logs');
  const [logData, setLogData] = useState<BatchLogResponse | null>(null);

  const pageTitle = useMemo(() => {
    if (view === 'dashboard') return 'Dashboard';
    if (view === 'trade_history') return '매매내역';
    if (view === 'data_status') return 'Data Status';
    if (view === 'closing') return 'Closing Bet V2';
    return '누적 성과';
  }, [view]);

  const pageSubtitle = useMemo(() => {
    if (view === 'dashboard') return '오늘 시장 상황과 추천 종목 요약을 조회합니다.';
    if (view === 'trade_history') return '보유 종목과 실제 체결내역, 기간별 손익을 계좌 기준으로 조회합니다.';
    if (view === 'data_status') return '배치 상태와 로그를 일반적인 웹페이지처럼 조회합니다.';
    if (view === 'closing') return '배치가 끝난 최종 결과만 빠르게 조회합니다.';
    return '최종 signal 결과를 기반으로 누적 성과를 조회합니다.';
  }, [view]);

  async function refreshDashboard(forceRefresh = false) {
    if (!dashboardData) {
      setContentLoading(true);
    }
    setDashboardRefreshing(true);
    try {
      setDashboardData(await getDashboard(false, forceRefresh));
    } finally {
      setContentLoading(false);
      setDashboardRefreshing(false);
    }
  }

  async function refreshTradeHistory() {
    if (!tradeHistoryData) {
      setContentLoading(true);
    }
    setTradeHistoryRefreshing(true);
    try {
      const params = new URLSearchParams({
        date_from: tradeDateFrom,
        date_to: tradeDateTo,
        side: tradeSideFilter,
        status: tradeStatusFilter,
        q: tradeQuery,
      });
      setTradeHistoryData(await getTradeHistory(params));
    } finally {
      setContentLoading(false);
      setTradeHistoryRefreshing(false);
    }
  }

  async function refreshBatchStatus() {
    setStatusLoading(true);
    try {
      setBatchData(await getBatches());
    } finally {
      setStatusLoading(false);
    }
  }

  async function refreshClosing() {
    setContentLoading(true);
    try {
      const params = new URLSearchParams({
        date: selectedDate,
        grade: gradeFilter,
        q: closingQuery,
        page: String(closingPage),
        page_size: '8',
      });
      setClosingData(await getClosingBet(params));
    } finally {
      setContentLoading(false);
    }
  }

  async function refreshPerformance() {
    if (!performanceData) {
      setContentLoading(true);
    }
    setPerformanceRefreshing(true);
    try {
      const params = new URLSearchParams({
        date_from: performanceDateFrom,
        date_to: performanceDateTo,
        grade: gradeFilter,
        outcome: performanceOutcome,
        q: performanceQuery,
        page: String(performancePage),
        page_size: '12',
      });
      setPerformanceData(await getPerformance(params));
    } finally {
      setContentLoading(false);
      setPerformanceRefreshing(false);
    }
  }

  async function handleQuickRefreshPerformance() {
    setPerformanceQuickRefreshing(true);
    try {
      const result = await quickRefreshPerformance(performanceDateFrom, performanceDateTo);
      setPerformanceRefreshInfo(result);
      await refreshPerformance();
    } finally {
      setPerformanceQuickRefreshing(false);
    }
  }

  async function handleOpenPreview(taskId: string) {
    const task = batchData?.tasks.find((item) => item.id === taskId);
    setPreviewTitle(task ? `${task.title} Preview` : 'Preview');
    setPreviewData(await getBatchPreview(taskId));
    setPreviewOpen(true);
  }

  async function handleOpenLogs(taskId: string) {
    const task = batchData?.tasks.find((item) => item.id === taskId);
    setLogTitle(task ? `${task.title} Logs` : 'Logs');
    setLogData(await getBatchLogs(taskId));
    setLogOpen(true);
  }

  async function handleRunTask(taskId: string) {
    await runBatch(taskId, batchSource);
    await refreshBatchStatus();
  }

  async function handleRunAll() {
    await runAllBatches(batchSource);
    await refreshBatchStatus();
  }

  useEffect(() => {
    getDates().then(setDates).catch(() => setDates({ dates: [], latest: null }));
  }, []);

  useEffect(() => {
    if (view === 'dashboard') {
      refreshDashboard(false).catch(console.error);
    }
  }, [view]);

  useEffect(() => {
    if (view === 'trade_history') {
      refreshTradeHistory().catch(console.error);
    }
  }, [view, tradeDateFrom, tradeDateTo, tradeSideFilter, tradeStatusFilter, tradeQuery]);

  useEffect(() => {
    if (view !== 'trade_history') {
      return;
    }
    const ms = autoRefreshMs(tradeAutoRefresh);
    if (!ms) {
      return;
    }
    const handle = window.setInterval(() => {
      refreshTradeHistory().catch(console.error);
    }, ms);
    return () => window.clearInterval(handle);
  }, [view, tradeAutoRefresh, tradeDateFrom, tradeDateTo, tradeSideFilter, tradeStatusFilter, tradeQuery]);

  useEffect(() => {
    if (view === 'data_status') {
      refreshBatchStatus().catch(console.error);
    }
  }, [view]);

  useEffect(() => {
    if (view === 'closing') {
      refreshClosing().catch(console.error);
    }
  }, [view, selectedDate, gradeFilter, closingPage, closingQuery]);

  useEffect(() => {
    if (view === 'performance') {
      refreshPerformance().catch(console.error);
    }
  }, [view, performanceDateFrom, performanceDateTo, gradeFilter, performanceOutcome, performancePage, performanceQuery]);

  return (
    <AppShell view={view} onChangeView={setView}>
      <div className="page-head">
        <div>
          <h1>{pageTitle}</h1>
          <p>{pageSubtitle}</p>
        </div>
        {view !== 'dashboard' && view !== 'data_status' ? (
          <div className="toolbar compact">
            <div className="toolbar-left">
              {view === 'closing' ? (
                <>
                  <select value={selectedDate} onChange={(event) => { setSelectedDate(event.target.value); setClosingPage(1); }}>
                    <option value="latest">latest</option>
                    {dates.dates.map((date) => <option key={date} value={date}>{date}</option>)}
                  </select>
                  <select value={gradeFilter} onChange={(event) => { setGradeFilter(event.target.value); setClosingPage(1); }}>
                    <option value="ALL">ALL</option>
                    <option value="S">S</option>
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                  </select>
                  <input
                    placeholder="종목명 또는 티커 검색"
                    value={closingQuery}
                    onChange={(event) => {
                      setClosingQuery(event.target.value);
                      setClosingPage(1);
                    }}
                  />
                </>
              ) : null}

              {view === 'performance' ? (
                <>
                  <input type="date" value={performanceDateFrom} onChange={(event) => { setPerformanceDateFrom(event.target.value); setPerformancePage(1); }} />
                  <input type="date" value={performanceDateTo} onChange={(event) => { setPerformanceDateTo(event.target.value); setPerformancePage(1); }} />
                  <select value={gradeFilter} onChange={(event) => { setGradeFilter(event.target.value); setPerformancePage(1); }}>
                    <option value="ALL">ALL</option>
                    <option value="S">S</option>
                    <option value="A">A</option>
                    <option value="B">B</option>
                    <option value="C">C</option>
                  </select>
                  <select value={performanceOutcome} onChange={(event) => { setPerformanceOutcome(event.target.value); setPerformancePage(1); }}>
                    <option value="ALL">ALL</option>
                    <option value="WIN">WIN</option>
                    <option value="LOSS">LOSS</option>
                    <option value="OPEN">OPEN</option>
                  </select>
                  <input
                    placeholder="성과 검색"
                    value={performanceQuery}
                    onChange={(event) => {
                      setPerformanceQuery(event.target.value);
                      setPerformancePage(1);
                    }}
                  />
                </>
              ) : null}

              {view === 'trade_history' ? (
                <>
                  <input type="date" value={tradeDateFrom} onChange={(event) => setTradeDateFrom(event.target.value)} />
                  <input type="date" value={tradeDateTo} onChange={(event) => setTradeDateTo(event.target.value)} />
                  <select value={tradeSideFilter} onChange={(event) => setTradeSideFilter(event.target.value)}>
                    <option value="ALL">ALL</option>
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                  </select>
                  <select value={tradeStatusFilter} onChange={(event) => setTradeStatusFilter(event.target.value)}>
                    <option value="ALL">ALL</option>
                    <option value="체결">체결</option>
                    <option value="접수">접수</option>
                    <option value="확인">확인</option>
                  </select>
                  <input
                    placeholder="종목명, 티커, 주문번호 검색"
                    value={tradeQuery}
                    onChange={(event) => setTradeQuery(event.target.value)}
                  />
                </>
              ) : null}
            </div>
            {view === 'trade_history' ? (
              <div className="toolbar-left">
                <select value={tradeAutoRefresh} onChange={(event) => setTradeAutoRefresh(event.target.value)}>
                  <option value="MANUAL">수동</option>
                  <option value="30S">30초</option>
                  <option value="1M">1분</option>
                  <option value="5M">5분</option>
                  <option value="10M">10분</option>
                </select>
                <button className="ghost-button" onClick={() => refreshTradeHistory()} disabled={tradeHistoryRefreshing}>
                  {tradeHistoryRefreshing ? '새로고침 중...' : '새로고침'}
                </button>
              </div>
            ) : null}
            {view === 'closing' ? (
              <button className="ghost-button" onClick={() => refreshClosing()} disabled={contentLoading}>
                새로고침
              </button>
            ) : null}
            {view === 'performance' ? (
              <button className="ghost-button" onClick={() => refreshPerformance()} disabled={performanceRefreshing}>
                {performanceRefreshing ? '새로고침 중...' : '새로고침'}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {view === 'dashboard' ? (
        <DashboardPage
          loading={contentLoading}
          data={dashboardData}
          onRefresh={() => refreshDashboard(true)}
          onRefreshAccount={() => undefined}
          dashboardRefreshing={dashboardRefreshing}
          accountRefreshing={false}
        />
      ) : null}

      {view === 'trade_history' ? (
        <TradeHistoryPage
          loading={contentLoading}
          data={tradeHistoryData}
        />
      ) : null}

      {view === 'data_status' ? (
        <DataStatusPage
          loading={statusLoading}
          data={batchData}
          source={batchSource}
          previewOpen={previewOpen}
          preview={previewData}
          previewTitle={previewTitle}
          logOpen={logOpen}
          log={logData}
          logTitle={logTitle}
          onRefresh={refreshBatchStatus}
          onChangeSource={setBatchSource}
          onRunTask={handleRunTask}
          onRunAll={handleRunAll}
          onOpenPreview={handleOpenPreview}
          onOpenLogs={handleOpenLogs}
          onClosePreview={() => setPreviewOpen(false)}
          onCloseLog={() => setLogOpen(false)}
        />
      ) : null}

      {view === 'closing' ? <ClosingBetPage loading={contentLoading} data={closingData} onPageChange={setClosingPage} /> : null}
      {view === 'performance' ? (
        <PerformancePage
          loading={contentLoading}
          data={performanceData}
          onPageChange={setPerformancePage}
          onQuickRefresh={handleQuickRefreshPerformance}
          quickRefreshing={performanceQuickRefreshing}
          refreshInfo={performanceRefreshInfo}
        />
      ) : null}
    </AppShell>
  );
}

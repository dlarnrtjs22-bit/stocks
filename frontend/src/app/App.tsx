import React, { useEffect, useMemo, useState } from 'react';
import { getBatchLogs, getBatchPreview, getBatches, getClosingBet, getDashboard, getDates, getPerformance, quickRefreshPerformance, runAllBatches, runBatch } from '../api/endpoints';
import { AppShell } from '../components/layout/AppShell';
import { DashboardPage } from '../pages/DashboardPage';
import { DataStatusPage } from '../pages/DataStatusPage';
import { ClosingBetPage } from '../pages/ClosingBetPage';
import { PerformancePage } from '../pages/PerformancePage';
import type { BatchListResponse, BatchLogResponse, ClosingBetResponse, DashboardResponse, DateListResponse, PerformanceRefreshResponse, PerformanceResponse, PreviewResponse, ViewKey } from '../types/api';

// 이 컴포넌트는 새 프로젝트 프론트 전체 상태를 관리한다.
export function App() {
  const [view, setView] = useState<ViewKey>('dashboard');
  const [batchSource, setBatchSource] = useState('naver');
  const [dates, setDates] = useState<DateListResponse>({ dates: [], latest: null });
  const [selectedDate, setSelectedDate] = useState('latest');
  const [gradeFilter, setGradeFilter] = useState('ALL');
  const [performanceOutcome, setPerformanceOutcome] = useState('ALL');
  const [closingPage, setClosingPage] = useState(1);
  const [performancePage, setPerformancePage] = useState(1);
  const [closingQuery, setClosingQuery] = useState('');
  const [performanceQuery, setPerformanceQuery] = useState('');
  const [statusLoading, setStatusLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [batchData, setBatchData] = useState<BatchListResponse | null>(null);
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [closingData, setClosingData] = useState<ClosingBetResponse | null>(null);
  const [performanceData, setPerformanceData] = useState<PerformanceResponse | null>(null);
  const [performanceRefreshInfo, setPerformanceRefreshInfo] = useState<PerformanceRefreshResponse | null>(null);
  const [dashboardRefreshing, setDashboardRefreshing] = useState(false);
  const [accountRefreshing, setAccountRefreshing] = useState(false);
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
    if (view === 'data_status') return 'Data Status';
    if (view === 'closing') return 'Closing Bet V2';
    return '누적 성과';
  }, [view]);

  const pageSubtitle = useMemo(() => {
    if (view === 'dashboard') return '오늘 시장 상황과 추천 2종목 심층 리포트를 조회합니다.';
    if (view === 'data_status') return '배치 상태와 로그를 일반적인 웹페이지처럼 조회합니다.';
    if (view === 'closing') return '배치가 끝난 최종 결과만 빠르게 조회합니다.';
    return '최종 signal 결과를 기반으로 누적 성과를 조회합니다.';
  }, [view]);

  async function refreshDashboard(refreshAccount = false) {
    if (!dashboardData) {
      setContentLoading(true);
    }
    if (refreshAccount) {
      setAccountRefreshing(true);
    } else {
      setDashboardRefreshing(true);
    }
    try {
      setDashboardData(await getDashboard(refreshAccount));
    } finally {
      setContentLoading(false);
      setDashboardRefreshing(false);
      setAccountRefreshing(false);
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
        date: selectedDate,
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
      const result = await quickRefreshPerformance(selectedDate);
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
  }, [view, selectedDate, gradeFilter, performanceOutcome, performancePage, performanceQuery]);

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
              <select value={selectedDate} onChange={(event) => { setSelectedDate(event.target.value); setClosingPage(1); setPerformancePage(1); }}>
                <option value="latest">latest</option>
                {dates.dates.map((date) => <option key={date} value={date}>{date}</option>)}
              </select>
              <select value={gradeFilter} onChange={(event) => { setGradeFilter(event.target.value); setClosingPage(1); setPerformancePage(1); }}>
                <option value="ALL">ALL</option>
                <option value="S">S</option>
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
              </select>
              {view === 'performance' ? (
                <select value={performanceOutcome} onChange={(event) => { setPerformanceOutcome(event.target.value); setPerformancePage(1); }}>
                  <option value="ALL">ALL</option>
                  <option value="WIN">WIN</option>
                  <option value="LOSS">LOSS</option>
                  <option value="OPEN">OPEN</option>
                </select>
              ) : null}
              <input
                placeholder={view === 'closing' ? '종목명 또는 티커 검색' : '성과 검색'}
                value={view === 'closing' ? closingQuery : performanceQuery}
                onChange={(event) => {
                  if (view === 'closing') {
                    setClosingQuery(event.target.value);
                    setClosingPage(1);
                  } else {
                    setPerformanceQuery(event.target.value);
                    setPerformancePage(1);
                  }
                }}
              />
            </div>
            <button className="ghost-button" onClick={() => view === 'closing' ? refreshClosing() : refreshPerformance()} disabled={performanceRefreshing}>
              {performanceRefreshing ? '새로고침 중...' : '새로고침'}
            </button>
          </div>
        ) : null}
      </div>

      {view === 'dashboard' ? (
        <DashboardPage
          loading={contentLoading}
          data={dashboardData}
          onRefresh={() => refreshDashboard(false)}
          onRefreshAccount={() => refreshDashboard(true)}
          dashboardRefreshing={dashboardRefreshing}
          accountRefreshing={accountRefreshing}
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

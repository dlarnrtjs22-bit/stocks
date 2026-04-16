import React from 'react';
import type { PerformanceRefreshResponse, PerformanceResponse } from '../../types/api';
import { fmtSignedPercent, fmtTimeHm } from '../../app/formatters';
import { Pager } from '../common/Pager';

// 이 컴포넌트는 누적 성과 요약과 테이블을 렌더링한다.
interface PerformanceViewProps {
  loading: boolean;
  data?: PerformanceResponse | null;
  onPageChange: (page: number) => void;
  onQuickRefresh: () => void;
  quickRefreshing: boolean;
  refreshInfo?: PerformanceRefreshResponse | null;
}

export function PerformanceView({ loading, data, onPageChange, onQuickRefresh, quickRefreshing, refreshInfo }: PerformanceViewProps) {
  if (loading && !data) {
    return <div className="card-panel">누적 성과 데이터를 불러오는 중입니다.</div>;
  }
  if (!data) {
    return <div className="card-panel">데이터 없음</div>;
  }

  const formatPrice = (value?: number | null) => (value ? value.toLocaleString('ko-KR') : '-');
  const formatRoi = (value?: number | null) => (value === null || value === undefined ? '-' : fmtSignedPercent(value));
  const formatOutcome = (value: string) => (value === 'WIN' ? 'Win' : value === 'LOSS' ? 'Loss' : 'Open');
  const betterLabel = data.comparison.better_slot === '08'
    ? '08시 NXT 우세'
    : data.comparison.better_slot === '09'
      ? '09시 정규장 우세'
      : '동률/평가대기';
  const isRolling7d = data.basis?.request_date === 'latest(7d)';

  return (
    <section className="section-stack">
      {isRolling7d ? (
        <div className="inline-status">누적 성과 기본 조회는 금일 포함 최근 7거래일 기준입니다.</div>
      ) : null}
      <div className="metric-box-row four">
        <div className="metric-box"><div className="metric-label">TOTAL SIGNALS</div><div className="metric-value">{data.summary.total_signals}</div></div>
        <div className="metric-box"><div className="metric-label">08시 NXT 승률</div><div className="metric-value">{data.summary_08.win_rate}%</div><div className="muted-text">W/L {data.summary_08.wins}/{data.summary_08.losses} / 평균 {fmtSignedPercent(data.summary_08.avg_roi)}</div></div>
        <div className="metric-box"><div className="metric-label">09시 정규장 승률</div><div className="metric-value">{data.summary_09.win_rate}%</div><div className="muted-text">W/L {data.summary_09.wins}/{data.summary_09.losses} / 평균 {fmtSignedPercent(data.summary_09.avg_roi)}</div></div>
        <div className="metric-box"><div className="metric-label">비교</div><div className="metric-value small">{betterLabel}</div><div className="muted-text">승률 차이 {data.comparison.edge_pct}%p</div></div>
      </div>
      <div className="card-panel">
        <div className="section-title">등급별 성과: 08시 / 09시 비교</div>
        <div className="grade-summary-grid">
          {data.grade_summary.map((item) => (
            <div className="metric-box" key={item.grade}>
              <div className="metric-label">{item.grade} Grade</div>
              <div className="metric-value">{item.count}</div>
              <div className="muted-text">08시 {item.win_rate_08}% / {fmtSignedPercent(item.avg_roi_08)} / W/L {item.wl_08}</div>
              <div className="muted-text">09시 {item.win_rate_09}% / {fmtSignedPercent(item.avg_roi_09)} / W/L {item.wl_09}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="card-panel table-panel">
        <div className="section-head-row">
          <div className="section-title">거래 내역: 추천가 대비 다음 거래일 08시/09시 평가</div>
          <button className="primary-button compact-button" onClick={onQuickRefresh} disabled={quickRefreshing}>
            {quickRefreshing ? '비교값 갱신 중...' : '비교값 빠른갱신'}
          </button>
        </div>
        {refreshInfo ? (
          <div className="inline-status">
            {refreshInfo.message} 08시 갱신 {refreshInfo.refreshed_08}건 / 09시 갱신 {refreshInfo.refreshed_09}건 / 추적 {refreshInfo.tracked_count}종목
          </div>
        ) : null}
        <table className="data-table">
          <thead>
            <tr>
              <th>등급</th>
              <th>종목명</th>
              <th>티커</th>
              <th>진입가</th>
              <th>매수일</th>
              <th>평가일</th>
              <th>08시 NXT</th>
              <th>08시 손익률</th>
              <th>09시 정규장</th>
              <th>09시 손익률</th>
              <th>점수</th>
            </tr>
          </thead>
          <tbody>
            {data.trades.map((trade) => (
              <tr key={trade.key}>
                <td>{trade.grade}</td>
                <td>{trade.name}</td>
                <td>{trade.ticker}</td>
                <td>
                  <div>{trade.entry.toLocaleString('ko-KR')}</div>
                  <div className="muted-text">{trade.entry_time ? `${fmtTimeHm(trade.entry_time)} 기준` : '-'}</div>
                </td>
                <td>{trade.buy_date ?? trade.date}</td>
                <td>{trade.eval_date ?? '-'}</td>
                <td>{formatPrice(trade.eval_08_price)} <span className={`outcome-pill ${trade.outcome_08.toLowerCase()}`}>{formatOutcome(trade.outcome_08)}</span></td>
                <td>{formatRoi(trade.roi_08)}</td>
                <td>{formatPrice(trade.eval_09_price)} <span className={`outcome-pill ${trade.outcome_09.toLowerCase()}`}>{formatOutcome(trade.outcome_09)}</span></td>
                <td>{formatRoi(trade.roi_09)}</td>
                <td>{trade.score}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager page={data.pagination.page} totalPages={data.pagination.total_pages} onChange={onPageChange} />
    </section>
  );
}

import React from 'react';
import { fmtCompactSigned, fmtDateTime, fmtNumber, fmtSigned, fmtSignedPercent, fmtSignedWon, fmtWon } from '../../app/formatters';
import type { DashboardResponse } from '../../types/api';

interface DashboardViewProps {
  loading: boolean;
  data?: DashboardResponse | null;
  onRefresh: () => void;
  onRefreshAccount: () => void;
  dashboardRefreshing: boolean;
  accountRefreshing: boolean;
}

export function DashboardView({
  loading,
  data,
  onRefresh,
  onRefreshAccount,
  dashboardRefreshing,
  accountRefreshing,
}: DashboardViewProps) {
  if (loading && !data) {
    return <div className="card-panel">대시보드 데이터를 불러오는 중입니다.</div>;
  }
  if (!data) {
    return <div className="card-panel">대시보드 데이터가 없습니다.</div>;
  }

  return (
    <section className="section-stack">
      <div className="toolbar compact">
        <div className="toolbar-left">
          <button className="ghost-button" onClick={onRefresh} disabled={dashboardRefreshing || accountRefreshing}>
            {dashboardRefreshing ? '대시보드 새로고침 중...' : '대시보드 새로고침'}
          </button>
          <button className="ghost-button" onClick={onRefreshAccount} disabled={dashboardRefreshing || accountRefreshing}>
            {accountRefreshing ? '계좌 동기화 중...' : '계좌 새로고침'}
          </button>
        </div>
      </div>

      <div className="dashboard-hero card-panel">
        <div className="dashboard-hero-copy">
          <div className="section-title">오늘 시장 상황</div>
          <div className="dashboard-date">{data.date || '-'}</div>
          <p>{data.market_summary}</p>
        </div>
        <div className="dashboard-market-grid">
          {data.markets.map((market) => (
            <div className="metric-box dashboard-market-box" key={market.market}>
              <div className="metric-label">{market.market_label}</div>
              <div className="metric-value">{fmtSignedPercent(market.change_pct)}</div>
              <div className="muted-text">지수 {fmtNumber(Math.round(market.index_value))}</div>
              <div className="muted-text">상승 {fmtNumber(market.rise_count)} / 하락 {fmtNumber(market.fall_count)}</div>
              <div className="muted-text">프로그램 {fmtCompactSigned(market.total_net)}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="dashboard-account card-panel">
        <div className="section-head-row">
          <div>
            <div className="section-title">계좌 연동</div>
            <div className="muted-text">계좌번호 {data.account.account_no || '-'}</div>
          </div>
        </div>
        {data.account.available ? (
          <>
            <div className="metric-box-row four">
              <div className="metric-box">
                <div className="metric-label">평가금액</div>
                <div className="metric-value">{fmtWon(data.account.total_eval_amt)}</div>
              </div>
              <div className="metric-box">
                <div className="metric-label">평가손익</div>
                <div className="metric-value">{fmtSignedWon(data.account.total_eval_profit)}</div>
              </div>
              <div className="metric-box">
                <div className="metric-label">실현손익</div>
                <div className="metric-value">{fmtSignedWon(data.account.realized_profit)}</div>
              </div>
              <div className="metric-box">
                <div className="metric-label">미체결</div>
                <div className="metric-value">{fmtNumber(data.account.unfilled_count)}</div>
              </div>
            </div>
            <div className="inline-status">
              {data.account.note || '계좌 응답이 연결되었습니다.'} 보유종목 {fmtNumber(data.account.holdings_count)}건 / 추정자산 {fmtWon(data.account.estimated_assets)}
            </div>
          </>
        ) : (
          <div className="muted-text">{data.account.note}</div>
        )}
      </div>

      <div>
        <div className="section-title">추천 후보 최대 5종목</div>
        {data.picks.length < 5 ? (
          <div className="muted-text">가격과 조건을 적용해 {data.picks.length}종목만 남겼습니다.</div>
        ) : null}
        <div className="dashboard-pick-grid">
          {data.picks.map((pick) => (
            <article className={`closing-card grade-${pick.grade.toLowerCase()} dashboard-pick-card`} key={pick.ticker}>
              <div className="closing-top-row">
                <div className="closing-badges">
                  <span className="tag">{pick.grade} 등급</span>
                  {pick.base_grade && pick.base_grade !== pick.grade ? <span className="tag">원등급 {pick.base_grade}</span> : null}
                  <span className="tag">{pick.market}</span>
                  <span className="tag">{pick.sector || '기타'}</span>
                  <span className="tag">{pick.decision_label || pick.decision_status}</span>
                </div>
                <div className="score-box">
                  <strong>{pick.score_total}</strong>
                  <span>/22</span>
                </div>
              </div>

              <div className="dashboard-pick-head">
                <div>
                  <h3>{pick.name}</h3>
                  <div className="ticker-text">{pick.ticker}</div>
                </div>
                <div className="dashboard-price-box">
                  <strong>{fmtSigned(pick.current_price)}</strong>
                  <span>{fmtSignedPercent(pick.change_pct)}</span>
                </div>
              </div>

              <div className="metric-box-row four dashboard-mini-grid">
                <div className="metric-box">
                  <div className="metric-label">거래대금</div>
                  <div className="metric-value small">{fmtWon(pick.trading_value)}</div>
                </div>
                <div className="metric-box">
                  <div className="metric-label">외인 당일</div>
                  <div className="metric-value small">{fmtCompactSigned(pick.foreign_1d)}</div>
                </div>
                <div className="metric-box">
                  <div className="metric-label">기관 당일</div>
                  <div className="metric-value small">{fmtCompactSigned(pick.inst_1d)}</div>
                </div>
                <div className="metric-box">
                  <div className="metric-label">외인 5일</div>
                  <div className="metric-value small">{fmtCompactSigned(pick.foreign_5d)}</div>
                </div>
                <div className="metric-box">
                  <div className="metric-label">기관 5일</div>
                  <div className="metric-value small">{fmtCompactSigned(pick.inst_5d)}</div>
                </div>
                <div className="metric-box">
                  <div className="metric-label">수집처</div>
                  <div className="metric-value small">{pick.venue || '-'}</div>
                </div>
              </div>

              <div className="dashboard-report-title">{pick.report_title || `${pick.name} 종합 리포트`}</div>
              <div className="analysis-box dashboard-report-body">{pick.report_body || pick.ai_summary}</div>

              <div className="dashboard-keypoints">
                {pick.key_points.map((point) => (
                  <div className="dashboard-keypoint" key={point}>{point}</div>
                ))}
              </div>

              <div className="context-box">
                <div>호가 불균형: {String(pick.intraday.orderbook_imbalance ?? '-')}</div>
                <div>체결강도: {String(pick.intraday.execution_strength ?? '-')}</div>
                <div>분봉 패턴: {pick.minute_pattern_label || String(pick.intraday.minute_pattern ?? '-')}</div>
              </div>

              <div className="news-block">
                <div className="news-title">리포트 근거</div>
                {pick.references.length ? (
                  pick.references.map((reference, index) => (
                    <a className="news-link" key={`${pick.ticker}-${index}`} href={String(reference.url || '#')} target="_blank" rel="noreferrer">
                      [{String(reference.source || 'Naver')}] {String(reference.title || '')}
                    </a>
                  ))
                ) : (
                  <div className="muted-text">참고 뉴스 없음</div>
                )}
              </div>
            </article>
          ))}
        </div>
      </div>

      <div className="muted-text">업데이트: {fmtDateTime(data.account.snapshot_time || data.markets[0]?.snapshot_time || null)}</div>
    </section>
  );
}

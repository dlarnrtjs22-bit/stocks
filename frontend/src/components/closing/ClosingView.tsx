import React from 'react';
import type { ClosingBetItem, ClosingBetResponse } from '../../types/api';
import { fmtCompactSigned, fmtSigned, fmtSignedPercent, fmtWonToEok } from '../../app/formatters';
import { Pager } from '../common/Pager';

const scoreLabels: Record<string, string> = {
  news: '뉴스',
  supply: '수급',
  chart: '차트',
  volume: '거래량',
  candle: '캔들',
  consolidation: '기간조정',
  market: '시황',
  program: '프로그램',
  sector: '섹터',
  leader: '대장주',
  intraday: '장중 압력',
  news_attention: '화제성',
};

// 이 컴포넌트는 종가배팅 카드 목록과 Featured 섹션을 렌더링한다.
interface ClosingViewProps {
  loading: boolean;
  data?: ClosingBetResponse | null;
  onPageChange: (page: number) => void;
}

function ClosingCard({ item, featured = false }: { item: ClosingBetItem; featured?: boolean }) {
  return (
    <article className={`closing-card grade-${item.grade.toLowerCase()} ${featured ? 'featured-card' : ''}`}>
      <div className="closing-top-row">
        <div className="closing-badges">
          <span className="tag">{item.grade} 등급</span>
          {item.base_grade && item.base_grade !== item.grade ? <span className="tag">원등급 {item.base_grade}</span> : null}
          <span className="tag">{item.market}</span>
          <span className="tag">#{item.global_rank}</span>
        </div>
        <div className="score-box">
          <strong>{item.score_total}</strong>
          <span>/{item.score_max}</span>
        </div>
      </div>
      <div className="closing-body">
        <div className="closing-left">
          <h3>{item.name}</h3>
          <div className="ticker-text">{item.ticker}</div>
          <div className="theme-row">
            {item.themes.map((theme) => (
              <span className="theme-pill" key={theme}>{theme}</span>
            ))}
          </div>
          <div className="price-list">
            <div><span>진입가</span><strong>{fmtSigned(item.entry_price)}</strong></div>
            <div><span>현재가</span><strong>{fmtSigned(item.current_price)} ({fmtSignedPercent(item.change_pct)})</strong></div>
            <div><span>목표가</span><strong className="accent-warm">{fmtSigned(item.target_price)}</strong></div>
            <div><span>손절가</span><strong className="accent-cool">{fmtSigned(item.stop_price)}</strong></div>
            <div><span>거래대금</span><strong>{fmtWonToEok(item.trading_value)}</strong></div>
          </div>
          <div className="metric-box-row three closing-stat-grid">
            <div className="metric-box closing-stat-box">
              <div className="metric-label">거래대금</div>
              <div className="metric-value closing-stat-value" title={fmtWonToEok(item.trading_value)}>{fmtWonToEok(item.trading_value)}</div>
            </div>
            <div className="metric-box closing-stat-box">
              <div className="metric-label">외인 당일</div>
              <div className="metric-value closing-stat-value accent-danger" title={fmtSigned(item.foreign_1d)}>{fmtCompactSigned(item.foreign_1d)}</div>
            </div>
            <div className="metric-box closing-stat-box">
              <div className="metric-label">기관 당일</div>
              <div className="metric-value closing-stat-value accent-success" title={fmtSigned(item.inst_1d)}>{fmtCompactSigned(item.inst_1d)}</div>
            </div>
            <div className="metric-box closing-stat-box">
              <div className="metric-label">외인 5일</div>
              <div className="metric-value closing-stat-value accent-danger" title={fmtSigned(item.foreign_5d)}>{fmtCompactSigned(item.foreign_5d)}</div>
            </div>
            <div className="metric-box closing-stat-box">
              <div className="metric-label">기관 5일</div>
              <div className="metric-value closing-stat-value accent-success" title={fmtSigned(item.inst_5d)}>{fmtCompactSigned(item.inst_5d)}</div>
            </div>
          </div>
          <div className="button-row left-align">
            <a className="ghost-button link-button" href={item.chart_url} target="_blank" rel="noreferrer">차트 보기</a>
          </div>
        </div>
        <div className="closing-center">
          <div className="analysis-title">AI 종합 분석</div>
          <div className="analysis-box">{item.ai_analysis}</div>
          <div className="opinion-row">
            <span className={item.analysis_status === 'OK' ? 'tag tag-success' : 'tag'}>{item.analysis_status_label || item.analysis_status}</span>
            <span className={item.ai_opinion === '매수' ? 'tag tag-success' : 'tag tag-danger'}>최종 의견: {item.ai_opinion}</span>
            <span className="tag">판정: {item.decision_label || item.decision_status}</span>
          </div>
          <div className="news-block">
            <div className="news-title">최근 뉴스 (Naver)</div>
            {item.references.length ? (
              item.references.map((reference, index) => (
                <a className="news-link" key={`${item.ticker}-${index}`} href={String(reference.url || '#')} target="_blank" rel="noreferrer">
                  [{String(reference.source || 'Naver')}] {String(reference.title || '')}
                </a>
              ))
            ) : (
              <div className="muted-text">참고 뉴스 없음</div>
            )}
          </div>
        </div>
        <div className="closing-right">
          {Object.entries(item.scores).map(([key, value]) => (
            <div className="score-row" key={key}>
              <div className="score-row-head">
                <span>{scoreLabels[key] || key}</span>
                <strong>{value}</strong>
              </div>
              <div className="score-bar">
                <div className="score-bar-fill" style={{ width: `${Math.min(100, value * 34)}%` }} />
              </div>
            </div>
          ))}
          <div className="context-box">
            <div>시황: {String(item.market_context.market_label || item.market || '-')} / {item.market_status_label || String(item.market_context.market_status || '-')}</div>
            <div>프로그램: {fmtWonToEok(Number(item.program_context.total_net || 0))}</div>
            <div>글로벌: {item.external_market_status_label || String(item.external_market_context.status || '-')} / 위험점수 {Number(item.external_market_context.risk_score || 0).toFixed(1)}</div>
            <div>분봉 패턴: {item.minute_pattern_label || '-'}</div>
          </div>
        </div>
      </div>
    </article>
  );
}

export function ClosingView({ loading, data, onPageChange }: ClosingViewProps) {
  if (loading && !data) {
    return <div className="card-panel">종가배팅 데이터를 불러오는 중입니다.</div>;
  }
  if (!data) {
    return <div className="card-panel">데이터 없음</div>;
  }

  return (
    <section>
      <div className="section-stack">
        <div>
          <div className="section-title">핵심 후보 5종목</div>
          <div className="featured-list">
            {data.featured_items.map((item) => (
              <ClosingCard key={`featured-${item.ticker}-${item.rank}`} item={item} featured />
            ))}
          </div>
        </div>
        <div>
          <div className="section-title">종가배팅 전체 후보</div>
          <div className="section-stack">
            {data.items.map((item) => (
              <ClosingCard key={`${item.ticker}-${item.rank}`} item={item} />
            ))}
          </div>
        </div>
        <Pager page={data.pagination.page} totalPages={data.pagination.total_pages} onChange={onPageChange} />
      </div>
    </section>
  );
}

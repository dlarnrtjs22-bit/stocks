import React from 'react';
import { fmtDateTime, fmtNumber, fmtSignedPercent, fmtSignedWon, fmtWon } from '../../app/formatters';
import type { TradeHistoryResponse } from '../../types/api';

interface TradeHistoryViewProps {
  loading: boolean;
  data?: TradeHistoryResponse | null;
}

export function TradeHistoryView({ loading, data }: TradeHistoryViewProps) {
  if (loading && !data) {
    return <div className="card-panel">매매내역 데이터를 불러오는 중입니다.</div>;
  }
  if (!data) {
    return <div className="card-panel">데이터 없음</div>;
  }

  return (
    <section className="section-stack">
      <div className="dashboard-account card-panel">
        <div className="section-head-row">
          <div>
            <div className="section-title">매매내역</div>
            <div className="muted-text">계좌번호 {data.account.account_no || '-'} / 갱신 {fmtDateTime(data.refreshed_at || data.account.snapshot_time || null)}</div>
          </div>
        </div>
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
            <div className="metric-label">추정자산</div>
            <div className="metric-value">{fmtWon(data.account.estimated_assets)}</div>
          </div>
        </div>
        <div className="metric-box-row four">
          <div className="metric-box">
            <div className="metric-label">보유종목</div>
            <div className="metric-value">{fmtNumber(data.account.holdings_count)}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">미체결</div>
            <div className="metric-value">{fmtNumber(data.account.unfilled_count)}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">총 미체결수량</div>
            <div className="metric-value">{fmtNumber(data.account.total_unfilled_qty)}</div>
          </div>
          <div className="metric-box">
            <div className="metric-label">전체 체결건수</div>
            <div className="metric-value">{fmtNumber(data.executions.length)}</div>
          </div>
        </div>
        <div className="inline-status">{data.account.note}</div>
      </div>

      <div className="card-panel table-panel">
        <div className="section-title">보유 종목</div>
        {data.account.positions.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>종목명</th>
                <th>티커</th>
                <th>보유수량</th>
                <th>주문가능</th>
                <th>평단가</th>
                <th>현재가</th>
                <th>수익률</th>
                <th>평가손익</th>
                <th>평가금액</th>
              </tr>
            </thead>
            <tbody>
              {data.account.positions.map((position) => (
                <tr key={`${position.ticker}-${position.stock_name}`}>
                  <td>{position.stock_name}</td>
                  <td>{position.ticker}</td>
                  <td>{fmtNumber(position.quantity)}</td>
                  <td>{fmtNumber(position.available_qty)}</td>
                  <td>{fmtWon(position.avg_price)}</td>
                  <td>{fmtWon(position.current_price)}</td>
                  <td>{fmtSignedPercent(position.profit_rate)}</td>
                  <td>{fmtSignedWon(position.profit_amount)}</td>
                  <td>{fmtWon(position.eval_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="muted-text">보유 종목 없음</div>
        )}
      </div>

      <div className="card-panel table-panel">
        <div className="section-title">일자별 손익</div>
        {data.daily_summary.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>일자</th>
                <th>매수금액</th>
                <th>매도금액</th>
                <th>실현손익</th>
                <th>수수료</th>
                <th>세금</th>
              </tr>
            </thead>
            <tbody>
              {data.daily_summary.map((item) => (
                <tr key={item.date}>
                  <td>{item.date}</td>
                  <td>{fmtWon(item.buy_amount)}</td>
                  <td>{fmtWon(item.sell_amount)}</td>
                  <td>{fmtSignedWon(item.realized_profit)}</td>
                  <td>{fmtWon(item.commission)}</td>
                  <td>{fmtWon(item.tax)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="muted-text">선택 구간 일자별 손익 없음</div>
        )}
      </div>

      <div className="card-panel table-panel">
        <div className="section-title">실제 체결내역</div>
        {data.executions.length ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>체결시각</th>
                <th>종목명</th>
                <th>티커</th>
                <th>구분</th>
                <th>상태</th>
                <th>거래소</th>
                <th>주문수량</th>
                <th>체결수량</th>
                <th>미체결</th>
                <th>주문가</th>
                <th>체결가</th>
                <th>수수료</th>
                <th>세금</th>
                <th>슬리피지</th>
                <th>주문번호</th>
              </tr>
            </thead>
            <tbody>
              {data.executions.map((item) => (
                <tr key={item.key}>
                  <td>
                    <div>{item.filled_time ? fmtDateTime(item.filled_time) : '-'}</div>
                    <div className="muted-text">{item.venue || '-'}</div>
                  </td>
                  <td>{item.stock_name}</td>
                  <td>{item.ticker}</td>
                  <td>{item.order_type}</td>
                  <td>{item.order_status}</td>
                  <td>{item.venue || '-'}</td>
                  <td>{fmtNumber(item.order_qty)}</td>
                  <td>{fmtNumber(item.filled_qty)}</td>
                  <td>{fmtNumber(item.unfilled_qty)}</td>
                  <td>{fmtWon(item.order_price)}</td>
                  <td>{fmtWon(item.filled_price)}</td>
                  <td>{fmtWon(item.fee)}</td>
                  <td>{fmtWon(item.tax)}</td>
                  <td>{fmtSignedPercent(item.slippage_bps / 100)}</td>
                  <td>
                    <div>{item.order_no}</div>
                    <div className="muted-text">{item.original_order_no || '-'}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="muted-text">선택 구간 체결내역 없음</div>
        )}
      </div>
    </section>
  );
}

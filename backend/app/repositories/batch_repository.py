from __future__ import annotations

# 이 파일은 배치 상태 화면과 Preview 조회를 담당한다.
from typing import Any

from backend.app.core.database import db_connection


# 이 리포지토리는 Data Status 화면 전용 조회를 담당한다.
class BatchRepository:
    # 이 메서드는 배치 상태 화면 카드 목록을 한 번의 view 조회로 반환한다.
    def fetch_batch_status_rows(self) -> list[dict[str, Any]]:
        sql = """
        select task_id, title, group_name, output_target, updated_at, max_data_time, records
        from vw_batch_status
        order by case task_id
          when 'daily_prices' then 1
          when 'institutional_trend' then 2
          when 'ai_analysis' then 3
          when 'market_context' then 4
          when 'program_trend' then 5
          when 'vcp_signals' then 6
          when 'ai_jongga_v2' then 7
          else 99
        end
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return list(cur.fetchall())

    # 이 메서드는 카드별 Preview 버튼에 필요한 샘플 데이터를 읽는다.
    def fetch_preview_rows(self, task_id: str, limit: int) -> tuple[list[str], list[dict[str, Any]]]:
        queries: dict[str, str] = {
            'daily_prices': "select trade_date, ticker, close_price, volume, trading_value from naver_ohlcv_1d order by trade_date desc, ticker limit %(limit)s",
            'institutional_trend': "select trade_date, ticker, foreign_net_buy, inst_net_buy, retail_net_buy from naver_flows_1d order by trade_date desc, ticker limit %(limit)s",
            'ai_analysis': "select ticker, published_at, source, title, relevance_score from naver_news_items order by published_at desc nulls last limit %(limit)s",
            'market_context': "select trade_date, market, market_label, change_pct, rise_count, fall_count from naver_market_context_1d order by trade_date desc, market limit %(limit)s",
            'program_trend': "select trade_date, market, total_buy, total_sell, total_net, non_arbitrage_net from naver_program_trend_1d order by trade_date desc, market limit %(limit)s",
            'vcp_signals': "select trade_date, ticker, signal, vcp_score, close_price, vol_ratio from naver_vcp_signals_latest order by trade_date desc, ticker limit %(limit)s",
            'ai_jongga_v2': "select run_date, signal_rank, stock_code, stock_name, grade, score_total, trading_value from vw_jongga_signal_read order by run_date desc, signal_rank asc limit %(limit)s",
        }
        sql = queries.get(task_id)
        if not sql:
            return [], []

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'limit': int(limit)})
                rows = list(cur.fetchall())

        if not rows:
            return [], []
        columns = list(rows[0].keys())
        return columns, rows


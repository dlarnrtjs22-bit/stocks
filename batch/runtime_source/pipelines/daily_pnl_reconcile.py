"""09:10 일일 P/L 집계 + kill switch 평가.

# Design Ref: Design §9.3 Module G — 일일 -5% 한도 도달 시 자동 차단
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("pnl_reconcile")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

    from backend.app.core.database import db_connection, open_db_pool
    try:
        open_db_pool()
    except Exception as exc:
        logger.error("DB 풀 초기화 실패: %s", exc)
        return 3
    from executor import guards

    target_date = args.date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    logger.info("reconcile %s", target_date)

    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS daily_pnl (
                        pnl_date DATE PRIMARY KEY,
                        gross_buy_krw BIGINT DEFAULT 0,
                        gross_sell_krw BIGINT DEFAULT 0,
                        realized_pnl_krw BIGINT DEFAULT 0,
                        realized_pct NUMERIC(6,3),
                        fee_krw BIGINT DEFAULT 0,
                        positions_open INT DEFAULT 0,
                        cumulative_pct NUMERIC(6,3),
                        kill_switch_hit BOOLEAN DEFAULT FALSE,
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                """)
                # 집계 — auto_orders 기반
                cur.execute("""
                    SELECT
                      SUM(CASE WHEN side='BUY'  THEN filled_qty*filled_avg_price ELSE 0 END) AS buy_krw,
                      SUM(CASE WHEN side='SELL' THEN filled_qty*filled_avg_price ELSE 0 END) AS sell_krw
                    FROM auto_orders
                    WHERE set_date = %s AND filled_qty > 0
                """, (target_date,))
                row = cur.fetchone() or {}
                buy_krw = int(row.get("buy_krw") or 0)
                sell_krw = int(row.get("sell_krw") or 0)
                realized = sell_krw - buy_krw
                realized_pct = (realized / buy_krw * 100.0) if buy_krw > 0 else 0.0

                cur.execute("""
                    INSERT INTO daily_pnl (pnl_date, gross_buy_krw, gross_sell_krw, realized_pnl_krw, realized_pct, cumulative_pct)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (pnl_date) DO UPDATE SET
                      gross_buy_krw=EXCLUDED.gross_buy_krw,
                      gross_sell_krw=EXCLUDED.gross_sell_krw,
                      realized_pnl_krw=EXCLUDED.realized_pnl_krw,
                      realized_pct=EXCLUDED.realized_pct,
                      cumulative_pct=EXCLUDED.cumulative_pct,
                      updated_at=now()
                """, (target_date, buy_krw, sell_krw, realized, realized_pct, realized_pct))

        logger.info("P/L: buy=%d sell=%d realized=%d (%.2f%%)", buy_krw, sell_krw, realized, realized_pct)

        # -5% 한도 도달 시 kill switch
        kill_hit = realized_pct <= guards.DAILY_LOSS_LIMIT_PCT
        if kill_hit:
            guards.disable_kill_switch()
            logger.warning("DAILY LOSS LIMIT hit (%.2f%% <= %.2f%%). kill switch disabled.", realized_pct, guards.DAILY_LOSS_LIMIT_PCT)

        # 실행 히스토리 기록
        try:
            from batch.runtime_source.utils.execution_history import record_event
            summary = f"P/L 집계: 매수 {buy_krw:,} / 매도 {sell_krw:,} / 실현 {realized:+,}원 ({realized_pct:+.2f}%)"
            if kill_hit:
                summary += " ⚠ 일일 -5% 한도 도달 → Kill Switch OFF"
            record_event(
                event_type="pnl_reconcile",
                summary=summary,
                details={
                    "buy_krw": buy_krw,
                    "sell_krw": sell_krw,
                    "realized_pnl_krw": realized,
                    "realized_pct": round(realized_pct, 3),
                    "kill_switch_hit": kill_hit,
                },
                target_date=target_date,
            )
        except Exception as exc:
            logger.warning("history record 실패: %s", exc)
        return 0
    except Exception as exc:
        logger.exception("reconcile failed: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

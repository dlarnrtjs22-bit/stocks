"""08:00 자동매도 진입점 (scheduler가 호출).

# Design Ref: Design §5.5 + §8 Module F

흐름:
  1. 전일 매수 포지션 로드 (auto_orders 테이블 or 키움 계좌 조회)
  2. 종목별로 execute_sell_schedule 호출 (08:00~09:00:30 전체 플로우)
  3. 긴급 손절 스레드는 trade_executor 내부에서 tick마다 체크
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BATCH_RUNTIME_ROOT = PROJECT_ROOT / "batch" / "runtime_source"
for _p in (PROJECT_ROOT, BATCH_RUNTIME_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


logger = logging.getLogger("runner_sell")


def load_yesterday_positions() -> list[dict]:
    """전일 매수한 포지션 리스트.
    간이 구현: auto_orders 테이블에서 BUY FILLED/PARTIAL 조회.
    실제 운영에서는 키움 계좌 잔고 API로 재확인 권장.
    """
    from backend.app.core.database import db_connection
    yesterday = (datetime.now(ZoneInfo("Asia/Seoul")).date() - timedelta(days=1)).isoformat()
    positions: list[dict] = []
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT stock_code,
                           SUM(filled_qty) AS qty,
                           AVG(NULLIF(filled_avg_price,0)) AS avg_price
                    FROM auto_orders
                    WHERE set_date = %s AND side='BUY' AND filled_qty > 0
                    GROUP BY stock_code
                """, (yesterday,))
                for row in cur.fetchall():
                    qty = int(row.get("qty") or 0)
                    if qty > 0:
                        positions.append({
                            "stock_code": row["stock_code"],
                            "qty": qty,
                            "avg_price": float(row.get("avg_price") or 0),
                        })
    except Exception as exc:
        logger.warning("auto_orders 로드 실패, 키움 계좌에서 재조회 필요: %s", exc)
    return positions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

    try:
        from backend.app.core.database import open_db_pool
        open_db_pool()
    except Exception as exc:
        logger.error("DB 풀 초기화 실패: %s", exc)
        return 3

    from executor.trade_executor import TradeExecutor
    from providers.kiwoom_order import KiwoomOrderClient
    from executor import guards

    logger.info("runner_sell dry_run=%s", args.dry_run)
    logger.info("guards: %s", guards.status())

    target_date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()

    def _history(event_type: str, summary: str, details: dict) -> None:
        try:
            from batch.runtime_source.utils.execution_history import record_event
            record_event(event_type=event_type, summary=summary, details=details, target_date=target_date)
        except Exception as exc:
            logger.warning("history record 실패: %s", exc)

    positions = load_yesterday_positions()
    if not positions:
        logger.info("전일 포지션 없음. 스킵.")
        _history("sell_skip", "매도 스킵: 전일 포지션 없음", {"reason": "no_positions"})
        return 0

    _history(
        "sell_tranche",
        f"매도 플로우 시작: {len(positions)}종목",
        {"phase": "start", "positions": [{"code": p["stock_code"], "qty": p["qty"], "avg": p.get("avg_price")} for p in positions]},
    )

    client = KiwoomOrderClient()
    executor = TradeExecutor(order_client=client)

    for pos in positions:
        code = pos["stock_code"]
        qty = int(pos["qty"])
        avg = float(pos.get("avg_price") or 0)
        logger.info("SELL %s qty=%d avg=%.0f", code, qty, avg)
        results = executor.execute_sell_schedule(
            position_qty=qty,
            stock_code=code,
            reference_close=int(avg),
            dry_run=args.dry_run,
        )
        for r in results:
            logger.info("  order: %s", r.to_dict())

        filled = sum(1 for r in results if str(r.status) in {"FILLED", "PARTIAL"})
        _history(
            "sell_tranche",
            f"매도 완료 {code}: {len(results)}건 주문 (체결 {filled})",
            {"phase": "end", "stock_code": code, "qty": qty, "avg_price": avg, "order_count": len(results), "filled": filled, "dry_run": args.dry_run},
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

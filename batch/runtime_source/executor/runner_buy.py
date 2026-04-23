"""19:50 자동매수 진입점 (scheduler가 호출).

# Design Ref: Design §5.4 + §7 Module E

흐름:
  1. candidate_set_v3 최신 스냅샷 로드 (Module C 결과)
  2. post_close_briefing 최신 action 반영 (Module D 결과)
  3. guards.check_allowed() → 실행/스킵/paper
  4. 예수금 조회 + compute_allocation
  5. BUY_TRANCHES 순차 실행 (wait_until 내장)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BATCH_RUNTIME_ROOT = PROJECT_ROOT / "batch" / "runtime_source"
for _p in (PROJECT_ROOT, BATCH_RUNTIME_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


logger = logging.getLogger("runner_buy")


def load_today_candidates(target_date: str) -> list["Candidate"]:
    from executor.trade_executor import Candidate
    from backend.app.core.database import db_connection

    candidates: list[Candidate] = []
    actions: dict[str, str] = {}

    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                # 최신 briefing action 반영 (있으면)
                cur.execute("""
                    SELECT DISTINCT ON (stock_code) stock_code, action
                    FROM post_close_briefing
                    WHERE brief_date = %s
                    ORDER BY stock_code, brief_time DESC
                """, (target_date,))
                for row in cur.fetchall():
                    actions[row["stock_code"]] = str(row.get("action") or "KEEP")

                # 최신 candidate_set 로드
                cur.execute("""
                    SELECT stock_code, stock_name, sector, entry_price_hint
                    FROM candidate_set_v3
                    WHERE set_date = %s
                    ORDER BY created_at DESC, rank
                """, (target_date,))
                seen = set()
                for row in cur.fetchall():
                    code = row["stock_code"]
                    if code in seen:
                        continue
                    seen.add(code)
                    candidates.append(Candidate(
                        stock_code=code,
                        name=row.get("stock_name") or "",
                        entry_hint=int(row.get("entry_price_hint") or 0),
                        action=actions.get(code, "KEEP"),
                        sector=row.get("sector") or "",
                    ))
                    if len(candidates) >= 2:
                        break
    except Exception as exc:
        logger.exception("candidate load failed: %s", exc)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", default=None)
    parser.add_argument("--skip-wait", action="store_true", help="테스트용: tranche 시간 대기 없이 즉시 3개 발주")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")

    # subprocess 기동 시 DB 풀 초기화
    try:
        from backend.app.core.database import open_db_pool
        open_db_pool()
    except Exception as exc:
        logger.error("DB 풀 초기화 실패: %s", exc)
        return 3

    target_date = args.date or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()

    from executor.trade_executor import TradeExecutor, compute_allocation
    from providers.kiwoom_order import KiwoomOrderClient
    from executor import guards

    logger.info("runner_buy %s dry_run=%s", target_date, args.dry_run)
    logger.info("guards: %s", guards.status())

    def _history(event_type: str, summary: str, details: dict) -> None:
        try:
            from batch.runtime_source.utils.execution_history import record_event
            record_event(event_type=event_type, summary=summary, details=details, target_date=target_date)
        except Exception as exc:
            logger.warning("history record 실패: %s", exc)

    candidates = load_today_candidates(target_date)
    if not candidates:
        logger.warning("후보 없음. 스킵.")
        _history("buy_skip", "매수 스킵: 후보 없음", {"reason": "no_candidates"})
        return 0

    # Module D DROP 후보가 섞여있는지 집계 (투명성용)
    drop_codes = [c.stock_code for c in candidates if c.action == "DROP"]
    halved_codes = [c.stock_code for c in candidates if c.action == "QTY_HALF"]

    client = KiwoomOrderClient()
    deposit = client.get_deposit()
    logger.info("예수금: %d원, 후보: %d종목", deposit, len(candidates))

    if deposit <= 0:
        logger.warning("예수금 0 또는 조회 실패. 스킵.")
        _history("buy_skip", f"매수 스킵: 예수금 조회 실패 (deposit={deposit})", {"reason": "deposit_fail", "deposit": deposit})
        return 1

    plans = compute_allocation(deposit, candidates)
    logger.info("배분: %s", [f"{c}:{p.total_qty}" for c, p in plans.items()])

    if not plans:
        logger.warning("배분 결과 없음. 스킵.")
        _history(
            "buy_skip",
            f"매수 스킵: 배분 결과 없음 (후보 {len(candidates)}개 중 DROP {len(drop_codes)}개)",
            {
                "reason": "no_plans",
                "candidate_count": len(candidates),
                "drop_codes": drop_codes,
                "halved_codes": halved_codes,
                "deposit": deposit,
            },
        )
        return 0

    _history(
        "buy_skip" if False else "buy_tranche",
        f"매수 플로우 시작: {len(plans)}종목 배분 완료 (예수금 {deposit:,}원)",
        {
            "phase": "start",
            "deposit": deposit,
            "plans": {code: p.total_qty for code, p in plans.items()},
            "drop_codes": drop_codes,
            "halved_codes": halved_codes,
        },
    )

    executor = TradeExecutor(order_client=client)
    results = executor.execute_buy_all_tranches(list(plans.values()), dry_run=args.dry_run, skip_wait=args.skip_wait)
    for r in results:
        logger.info("order: %s", r.to_dict())

    filled = sum(1 for r in results if str(r.status) in {"FILLED", "PARTIAL"})
    failed = sum(1 for r in results if str(r.status) in {"FAILED", "CANCELLED"})
    _history(
        "buy_tranche",
        f"매수 완료: 총 {len(results)}건 주문 (체결 {filled} / 실패 {failed})",
        {
            "phase": "end",
            "total_orders": len(results),
            "filled": filled,
            "failed": failed,
            "dry_run": args.dry_run,
            "results": [r.to_dict() for r in results],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

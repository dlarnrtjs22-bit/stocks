"""Module C: 15:30 자동 종가배팅 후보 추출 배치.

# Design Ref: Design §6.2 Module C — NXT 가능 종목 중 Top 2 섹터 다양성 선정
# Plan §6: 15:30 자동 배치 → candidate_set_v3 저장 → UI 실시간 반영

Usage:
    python -m batch.runtime_source.pipelines.daily_candidate_extract              # 오늘 기준
    python -m batch.runtime_source.pipelines.daily_candidate_extract --date 2026-04-23
    python -m batch.runtime_source.pipelines.daily_candidate_extract --dry-run    # 저장 안함

호출 체인:
  1. ClosingBetService로 오늘 featured/items 조회 (nxt_eligible 이미 채워져 있음)
  2. pick_selector.select_top_2_sector_diverse 로 Top 2 선정
  3. candidate_set_v3 테이블에 스냅샷 저장 (migration V2 필요)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _today_iso() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def _write_extract_status(status: dict[str, Any]) -> None:
    """결과 상태를 파일에 기록해서 Control API에서 읽게 한다."""
    state_dir = PROJECT_ROOT / ".bkit" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "last_extract_status.json"
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def run(date_arg: str | None = None, dry_run: bool = False) -> int:
    from backend.app.core.database import open_db_pool
    from backend.app.services.closing_bet_service import ClosingBetService
    from backend.app.services.pick_selector import select_top_2_sector_diverse
    from backend.app.services.view_helpers import safe_int

    # subprocess 실행 시 DB 풀이 없어서 초기화 필요 (main.py의 lifespan 미적용)
    try:
        open_db_pool()
    except Exception as exc:
        print(f"[extract] DB 풀 초기화 실패: {exc}", file=sys.stderr)
        return 3

    target_date = date_arg or _today_iso()
    run_ts = datetime.now(timezone.utc).isoformat()

    # === 오늘 run 존재 여부 가드 (DB 직접 쿼리) ===
    # ClosingBetService는 response.selected_date 에 fallback으로 오늘 날짜를 넣어서 속을 수 있음.
    # 실제 jongga_runs 테이블에 오늘자 run이 있는지 명시적으로 확인.
    from backend.app.core.database import db_connection
    actual_data_date = None
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT run_date FROM jongga_runs ORDER BY created_at DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row and row.get("run_date"):
                    actual_data_date = row["run_date"].isoformat()
    except Exception as exc:
        print(f"[extract] jongga_runs 조회 실패: {exc}", file=sys.stderr)
        _write_extract_status({
            "run_at": run_ts, "target_date": target_date, "actual_data_date": None,
            "status": "DB_ERROR", "picked_count": 0, "message": f"jongga_runs 조회 실패: {exc}",
        })
        return 2

    if actual_data_date != target_date:
        msg = (
            f"오늘({target_date}) jongga_runs 가 없음. 최신 데이터 날짜={actual_data_date}. "
            f"15:10 Run All 이 아직 완료되지 않았거나 실패했을 수 있음. Top 2 추출 스킵."
        )
        print(f"[extract] ⚠ STALE GUARD: {msg}", file=sys.stderr)
        _write_extract_status({
            "run_at": run_ts,
            "target_date": target_date,
            "actual_data_date": actual_data_date,
            "status": "STALE_SKIP",
            "picked_count": 0,
            "message": msg,
        })
        return 1

    # 오늘 run 존재 확인됨 → ClosingBetService로 후보 풀 로드
    svc = ClosingBetService()
    resp = svc.get_closing_bet(target_date, "ALL", "", 1, 200)

    # featured + items 모두 후보 풀에 포함 (dedup)
    all_rows = [item.model_dump() for item in resp.featured_items]
    seen = {r["ticker"] for r in all_rows}
    for item in resp.items:
        d = item.model_dump()
        if d["ticker"] not in seen:
            all_rows.append(d)
            seen.add(d["ticker"])

    # pick_selector는 stock_code 키를 사용하므로 ticker를 stock_code로 alias
    for r in all_rows:
        r.setdefault("stock_code", r.get("ticker", ""))
        r.setdefault("stock_name", r.get("name", ""))

    print(f"[extract] {target_date} 전체 후보 풀: {len(all_rows)}")
    nxt_count = sum(1 for r in all_rows if bool(r.get("nxt_eligible")))
    print(f"[extract] NXT 가능: {nxt_count}")

    picks = select_top_2_sector_diverse(all_rows, require_nxt_eligible=True, require_buy_status=True)
    print(f"[extract] Top 2 선정: {len(picks)}종목")
    for idx, p in enumerate(picks, 1):
        print(
            f"  [{idx}] {p.get('stock_code')} {p.get('stock_name') or p.get('name')} "
            f"sector={p.get('sector', '?')} grade={p.get('grade', '?')} "
            f"score={p.get('score_total')} change={p.get('change_pct')}% "
            f"nxt={p.get('nxt_eligible')} window={p.get('recommended_window')}"
        )

    if dry_run:
        print("[extract] --dry-run: DB 저장 생략")
        return 0

    # DB 저장 (candidate_set_v3 테이블 migration 존재 시에만)
    try:
        from backend.app.core.database import db_connection
        snapshot_ts = datetime.now(timezone.utc)
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS candidate_set_v3 (
                        set_date DATE NOT NULL,
                        rank INT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        stock_code VARCHAR(12) NOT NULL,
                        stock_name VARCHAR(64),
                        sector VARCHAR(64),
                        score_total INT,
                        base_grade VARCHAR(2),
                        final_grade VARCHAR(2),
                        change_pct NUMERIC(6,2),
                        trading_value BIGINT,
                        entry_price_hint NUMERIC(12,2),
                        nxt_eligible BOOLEAN,
                        recommended_window VARCHAR(16),
                        snapshot_json JSONB,
                        PRIMARY KEY (set_date, rank, created_at)
                    )
                """)
                for rank_idx, p in enumerate(picks, 1):
                    # UPSERT: 같은 날 같은 종목은 최신 스냅샷으로 덮어쓴다 (uq_candidate_set_v3_date_code 인덱스).
                    # extract 가 수동/자동 중복 실행돼도 중복 row 가 쌓이지 않음.
                    cur.execute(
                        """
                        INSERT INTO candidate_set_v3
                          (set_date, rank, created_at, stock_code, stock_name, sector,
                           score_total, base_grade, final_grade, change_pct, trading_value,
                           entry_price_hint, nxt_eligible, recommended_window, snapshot_json)
                        VALUES
                          (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (set_date, stock_code) DO UPDATE SET
                          rank=EXCLUDED.rank,
                          created_at=EXCLUDED.created_at,
                          stock_name=EXCLUDED.stock_name,
                          sector=EXCLUDED.sector,
                          score_total=EXCLUDED.score_total,
                          base_grade=EXCLUDED.base_grade,
                          final_grade=EXCLUDED.final_grade,
                          change_pct=EXCLUDED.change_pct,
                          trading_value=EXCLUDED.trading_value,
                          entry_price_hint=EXCLUDED.entry_price_hint,
                          nxt_eligible=EXCLUDED.nxt_eligible,
                          recommended_window=EXCLUDED.recommended_window,
                          snapshot_json=EXCLUDED.snapshot_json
                        """,
                        (
                            target_date, rank_idx, snapshot_ts,
                            p.get("stock_code"), p.get("stock_name") or p.get("name"),
                            p.get("sector"),
                            safe_int(p.get("score_total")),
                            p.get("base_grade"), p.get("grade"),
                            float(p.get("change_pct") or 0),
                            safe_int(p.get("trading_value")),
                            float(p.get("entry_price") or p.get("current_price") or 0),
                            bool(p.get("nxt_eligible")),
                            p.get("recommended_window"),
                            json.dumps(p, default=str, ensure_ascii=False),
                        ),
                    )
        print(f"[extract] candidate_set_v3에 {len(picks)}건 저장 완료 ({snapshot_ts.isoformat()})")
    except Exception as exc:
        print(f"[extract] DB 저장 실패: {exc}", file=sys.stderr)
        _write_extract_status({
            "run_at": run_ts,
            "target_date": target_date,
            "actual_data_date": actual_data_date,
            "status": "DB_ERROR",
            "picked_count": len(picks),
            "message": str(exc),
        })
        return 2

    # 성공 상태 기록
    _write_extract_status({
        "run_at": run_ts,
        "target_date": target_date,
        "actual_data_date": actual_data_date,
        "status": "OK" if picks else "NO_CANDIDATES",
        "picked_count": len(picks),
        "message": (
            f"{len(picks)}종목 저장" if picks
            else "NXT 가능 + 매수 판정 후보 0건 (오늘 매매 없음)"
        ),
    })

    # 실행 히스토리 기록
    try:
        from batch.runtime_source.utils.execution_history import record_event
        if picks:
            tickers_str = ", ".join(f"{p.get('stock_code')}({p.get('stock_name') or ''})" for p in picks[:3])
            record_event(
                event_type="candidate_extract",
                summary=f"Top {len(picks)} 후보 저장: {tickers_str}",
                details={
                    "picked_count": len(picks),
                    "tickers": [p.get("stock_code") for p in picks],
                    "scores": [p.get("score_total") for p in picks],
                    "grades": [p.get("grade") for p in picks],
                    "opinions": [p.get("ai_opinion") for p in picks],
                    "actual_data_date": actual_data_date,
                },
                target_date=target_date,
            )
        else:
            record_event(
                event_type="candidate_extract",
                summary="후보 0건 — 매수 판정 통과 종목 없음",
                details={"picked_count": 0, "actual_data_date": actual_data_date},
                target_date=target_date,
            )
    except Exception as exc:
        print(f"[extract] 히스토리 기록 실패 (무시): {exc}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Module C: 15:30 자동 후보 추출")
    parser.add_argument("--date", default=None, help="기준일 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 안함")
    args = parser.parse_args()
    return run(date_arg=args.date, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())

"""async vs sync 키움 클라이언트 성능 벤치마크.

# Design Ref: Design §10.3 — 15:30 run 90초 / 19:30 재평가 15초 목표
# Plan SC: 배치 수집 속도 전면 개선

Usage:
    python -m batch.scripts.bench_async_client --n 20 --mode both
    python -m batch.scripts.bench_async_client --n 50 --mode async --concurrency 16
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1] / "runtime_source"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from providers.kiwoom_client import KiwoomAPIError, KiwoomRESTClient
from providers.kiwoom_client_async import AsyncKiwoomClient


# 벤치 대상: 일봉 조회 (가벼운 호출)
BENCH_PATH = "/api/dostk/chart"
BENCH_API_ID = "ka10080"


def _sample_codes(n: int) -> list[str]:
    """NXT 가능 종목 CSV에서 샘플링."""
    csv_path = ROOT_DIR.parents[1] / "data" / "nxt_tickers.csv"
    codes: list[str] = []
    if csv_path.exists():
        for line in csv_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("stock_code"):
                continue
            code = line.split(",")[0].strip()
            if code.isdigit() and len(code) == 6:
                codes.append(code)
    # 부족하면 샘플 코드로 보충
    while len(codes) < n:
        codes.extend(["005930", "000660", "035420", "035720", "005380"])
    return codes[:n]


def _payload(code: str, base_dt: str) -> dict:
    return {
        "stk_cd": code,
        "tic_scope": "5",
        "upd_stkpc_tp": "1",
        "base_dt": base_dt,
    }


def bench_sync(codes: list[str], base_dt: str) -> tuple[float, int, int]:
    client = KiwoomRESTClient()
    start = time.time()
    ok = 0
    fail = 0
    for code in codes:
        try:
            client.request(BENCH_PATH, BENCH_API_ID, _payload(code, base_dt))
            ok += 1
        except KiwoomAPIError as exc:
            fail += 1
            logging.warning("sync fail %s: %s", code, exc)
    return time.time() - start, ok, fail


async def bench_async(codes: list[str], base_dt: str, concurrency: int) -> tuple[float, int, int, dict]:
    async with AsyncKiwoomClient(concurrency=concurrency) as client:
        requests = [(BENCH_PATH, BENCH_API_ID, _payload(code, base_dt)) for code in codes]
        start = time.time()
        results = await client.gather(requests)
        elapsed = time.time() - start
        ok = sum(1 for r in results if not isinstance(r, Exception))
        fail = sum(1 for r in results if isinstance(r, Exception))
        return elapsed, ok, fail, client.stats.as_dict()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10, help="요청 수")
    parser.add_argument("--mode", choices=["sync", "async", "both"], default="both")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--base-dt", default=time.strftime("%Y%m%d"))
    args = parser.parse_args()

    codes = _sample_codes(args.n)
    print(f"[bench] n={len(codes)} base_dt={args.base_dt} concurrency={args.concurrency}")

    if args.mode in ("sync", "both"):
        print("[bench] running SYNC...")
        elapsed, ok, fail = bench_sync(codes, args.base_dt)
        print(f"[bench] SYNC: {elapsed:.2f}s  ok={ok} fail={fail}  qps={ok/elapsed:.2f}")

    if args.mode in ("async", "both"):
        print("[bench] running ASYNC...")
        elapsed, ok, fail, stats = asyncio.run(
            bench_async(codes, args.base_dt, args.concurrency)
        )
        print(f"[bench] ASYNC: {elapsed:.2f}s  ok={ok} fail={fail}  stats={stats}")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())

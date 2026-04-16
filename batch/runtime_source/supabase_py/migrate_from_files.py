from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pandas as pd

from supabase_py.repository import SupabaseRepository


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"ticker": str})


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    data_dir = base / "data"
    naver = data_dir / "naver"

    repo = SupabaseRepository.from_env()

    universe = _read_csv(naver / "universe.csv")
    ohlcv = _read_csv(naver / "ohlcv_1d.csv")
    flows = _read_csv(naver / "flows_1d.csv")
    news = _read_csv(naver / "news_items.csv")
    snapshot = _read_csv(naver / "latest_snapshot.csv")
    vcp = _read_csv(naver / "vcp_signals_latest.csv")

    print("[backfill] universe", repo.upsert_universe(universe))
    print("[backfill] ohlcv", repo.upsert_ohlcv(ohlcv))
    print("[backfill] flows", repo.upsert_flows(flows))
    print("[backfill] news", repo.upsert_news(news))
    print("[backfill] snapshot", repo.upsert_snapshot(snapshot))
    print("[backfill] vcp", repo.upsert_vcp_signals(vcp))

    run_files = sorted(glob.glob(str(data_dir / "jongga_v2_results_*.json")))
    if not run_files:
        latest = data_dir / "jongga_v2_latest.json"
        if latest.exists():
            run_files = [str(latest)]

    inserted = 0
    for p in run_files:
        try:
            payload = json.loads(Path(p).read_text(encoding="utf-8"))
            repo.save_screener_result(payload)
            inserted += 1
        except Exception as e:
            print(f"[backfill] skip {os.path.basename(p)}: {e}")

    print(f"[backfill] jongga_runs inserted: {inserted}")
    print("[backfill] done")


if __name__ == "__main__":
    main()

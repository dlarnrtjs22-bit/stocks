from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from supabase_py.db import is_supabase_backend
from supabase_py.repository import SupabaseRepository


def _compute_vcp_signals(ohlcv: pd.DataFrame, top: int) -> pd.DataFrame:
    if ohlcv.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "ticker",
                "signal",
                "vcp_score",
                "close",
                "volume",
                "ma20",
                "vol_ratio",
            ]
        )

    df = ohlcv.copy()
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["close", "volume"]:
        if c not in df.columns:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["date", "close", "volume"]).sort_values(["ticker", "date"])

    rows = []
    for ticker, g in df.groupby("ticker"):
        if len(g) < 30:
            continue

        tail = g.tail(30).copy()
        latest = tail.iloc[-1]
        recent = tail.tail(5)
        prev = tail.iloc[-25:-5]

        if prev.empty or recent.empty:
            continue

        ma20 = float(tail["close"].tail(20).mean())
        close = float(latest["close"])
        volume = float(latest["volume"])

        prev_vol = float(prev["close"].pct_change().dropna().std() or 0.0)
        recent_vol = float(recent["close"].pct_change().dropna().std() or 0.0)
        vol_ratio = (recent_vol / prev_vol) if prev_vol > 0 else 99.0

        contraction = max(0.0, min(1.0, 1.0 - vol_ratio))
        trend = 1.0 if close >= ma20 else 0.0
        liq = min(1.0, volume / 3_000_000.0)
        score = round((contraction * 0.5 + trend * 0.3 + liq * 0.2) * 100, 1)

        signal = "WATCH"
        if score >= 70:
            signal = "VCP_READY"
        elif score >= 55:
            signal = "SETUP"

        rows.append(
            {
                "date": latest["date"].date().isoformat(),
                "ticker": ticker,
                "signal": signal,
                "vcp_score": score,
                "close": round(close, 2),
                "volume": int(volume),
                "ma20": round(ma20, 2),
                "vol_ratio": round(vol_ratio, 4),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out = out.sort_values(["vcp_score", "volume"], ascending=[False, False]).head(top)
    return out.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build simple VCP signal table from ohlcv data")
    parser.add_argument("--data-dir", default="data/naver")
    parser.add_argument("--top", type=int, default=400)
    parser.add_argument(
        "--refresh-today",
        default=os.getenv("BATCH_REFRESH_TODAY", "1"),
        help="1/true to replace current signal trade_date rows before upsert",
    )
    args = parser.parse_args()

    base = Path(args.data_dir)
    out_path = base / "vcp_signals_latest.csv"
    export_files = str(os.getenv("EXPORT_LOCAL_FILES", "0")).strip() in {"1", "true", "TRUE"}

    if not is_supabase_backend():
        raise SystemExit("DB backend is required. Set STORAGE_BACKEND=supabase and SUPABASE_DATABASE_URL")

    repo = SupabaseRepository.from_env()
    ohlcv = repo.load_ohlcv_df()
    result = _compute_vcp_signals(ohlcv, top=max(1, int(args.top)))
    refresh_today = str(args.refresh_today).strip().lower() in {"1", "true", "yes", "y", "on"}
    if refresh_today and not result.empty and "date" in result.columns:
        date_series = pd.to_datetime(result["date"], errors="coerce")
        dates = sorted({d.date() for d in date_series if pd.notna(d)})
        if dates:
            deleted = repo.delete_trade_dates("naver_vcp_signals_latest", dates)
            if deleted:
                print(f"vcp refresh delete(dates): {deleted}")
    repo.upsert_vcp_signals(result)
    if export_files:
        result.to_csv(out_path, index=False, encoding="utf-8-sig")

    print("saved: naver_vcp_signals_latest")
    print(f"rows: {len(result)}")
    print(f"updated_at: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()

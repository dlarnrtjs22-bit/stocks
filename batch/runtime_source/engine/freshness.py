from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from supabase_py.db import is_supabase_backend
from supabase_py.repository import SupabaseRepository


class DataReadinessError(RuntimeError):
    def __init__(self, status: str, report: Dict[str, Any]):
        self.status = status
        self.report = report
        super().__init__(f"{status}: {report.get('summary', '')}")


def _to_iso(dt: Optional[datetime]) -> str:
    return dt.isoformat() if isinstance(dt, datetime) else ""


def _file_meta(path: str) -> Dict[str, Any]:
    exists = os.path.exists(path)
    out: Dict[str, Any] = {
        "path": path,
        "exists": exists,
        "size_bytes": int(os.path.getsize(path)) if exists else 0,
        "mtime": "",
        "age_hours": None,
        "max_data_time": "",
        "status": "UNKNOWN",
        "reason": "",
    }
    if not exists:
        out["status"] = "MISSING"
        out["reason"] = "file not found"
        return out

    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    out["mtime"] = _to_iso(mtime)
    out["age_hours"] = round((datetime.now() - mtime).total_seconds() / 3600.0, 2)
    return out


def _read_max_time(path: str, col: str, *, is_datetime: bool) -> Tuple[Optional[datetime], str]:
    try:
        df = pd.read_csv(path, usecols=[col], dtype={col: str})
    except Exception as e:
        return None, f"read failed: {e}"

    if df.empty or col not in df.columns:
        return None, "empty or missing date column"

    raw = df[col].astype(str).str.strip()
    parsed = pd.to_datetime(raw, errors="coerce")
    parsed = parsed.dropna()
    if parsed.empty:
        return None, "no valid datetime values"

    latest = parsed.max()
    if not is_datetime:
        latest = latest.normalize()
    return latest.to_pydatetime(), ""


def check_data_freshness(data_dir: str, *, max_age_hours: Optional[int] = None) -> Dict[str, Any]:
    """Evaluate if required market data files are present and fresh enough for run."""
    max_age = int(max_age_hours or int(os.getenv("DATA_FRESHNESS_MAX_HOURS", "72") or 72))

    if is_supabase_backend():
        repo = SupabaseRepository.from_env()
        return repo.freshness_report(max_age_hours=max_age)

    naver_dir = os.path.join(data_dir, "naver")

    file_rules = {
        "latest_snapshot.csv": {"required": True, "date_col": "date", "is_datetime": False},
        "ohlcv_1d.csv": {"required": True, "date_col": "date", "is_datetime": False},
        "flows_1d.csv": {"required": True, "date_col": "date", "is_datetime": False},
        "news_items.csv": {"required": False, "date_col": "published_at", "is_datetime": True},
    }

    now = datetime.now()
    files: Dict[str, Any] = {}
    errors = []
    warnings = []
    required_times = []

    for filename, rule in file_rules.items():
        path = os.path.join(naver_dir, filename)
        meta = _file_meta(path)
        meta["required"] = bool(rule["required"])

        if not meta["exists"]:
            if rule["required"]:
                errors.append(f"{filename} missing")
            else:
                warnings.append(f"{filename} missing")
            files[filename] = meta
            continue

        max_time, reason = _read_max_time(path, str(rule["date_col"]), is_datetime=bool(rule["is_datetime"]))
        if max_time is None:
            meta["status"] = "INVALID"
            meta["reason"] = reason
            if rule["required"]:
                errors.append(f"{filename} invalid date column: {reason}")
            else:
                warnings.append(f"{filename} invalid date column: {reason}")
            files[filename] = meta
            continue

        meta["max_data_time"] = _to_iso(max_time)

        data_age_hours = round((now - max_time).total_seconds() / 3600.0, 2)
        stale_by_time = data_age_hours > max_age
        stale_by_mtime = (meta["age_hours"] is not None) and (float(meta["age_hours"]) > max_age)

        if stale_by_time or stale_by_mtime:
            meta["status"] = "STALE"
            if stale_by_time:
                meta["reason"] = f"max data time older than {max_age}h"
            else:
                meta["reason"] = f"file mtime older than {max_age}h"
            if rule["required"]:
                errors.append(f"{filename} stale")
            else:
                warnings.append(f"{filename} stale")
        else:
            meta["status"] = "OK"
            meta["reason"] = ""

        if rule["required"]:
            required_times.append((filename, max_time))
        files[filename] = meta

    reference_time = None
    if required_times:
        reference_time = max(ts for _, ts in required_times)
        tolerance = timedelta(days=1)
        for filename, ts in required_times:
            if reference_time - ts > tolerance:
                files[filename]["status"] = "STALE"
                files[filename]["reason"] = "date misaligned with other required market files"
                errors.append(f"{filename} date misaligned")

    if errors:
        if any("missing" in e or "invalid" in e for e in errors):
            status = "DATA_MISSING"
        else:
            status = "DATA_STALE"
    elif warnings:
        status = "OK_WITH_WARNINGS"
    else:
        status = "OK"

    return {
        "status": status,
        "checked_at": now.isoformat(),
        "max_age_hours": max_age,
        "reference_data_time": _to_iso(reference_time),
        "summary": "data ready" if status in {"OK", "OK_WITH_WARNINGS"} else "data not ready",
        "errors": errors,
        "warnings": warnings,
        "files": files,
    }


def assert_data_ready_for_run(data_dir: str) -> Dict[str, Any]:
    report = check_data_freshness(data_dir)
    allow_stale = str(os.getenv("ALLOW_STALE_DATA_RUN", "0")).strip() in {"1", "true", "TRUE"}
    if report["status"] in {"DATA_MISSING", "DATA_STALE"} and not allow_stale:
        raise DataReadinessError(report["status"], report)
    return report

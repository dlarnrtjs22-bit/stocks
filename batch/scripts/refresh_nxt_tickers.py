"""NXT 거래가능 종목 리스트 갱신 스크립트.

# Design Ref: Design §2.2 Module A - NXT 정적 리스트 관리
# Plan SC: 주 1회 월요일 06:00 자동 갱신, 7일 이상 미갱신 시 UI 배지 회색 처리

운영 방식:
- 기본: data/nxt_tickers.csv 를 수동 관리 (가장 안정적)
- 확장: nextrade.co.kr 거래대상종목 페이지를 파싱해서 자동 업데이트 (HTML 포맷 변동 리스크)

Usage:
    python -m batch.scripts.refresh_nxt_tickers                # 수동 모드 (CSV 유효성 검사만)
    python -m batch.scripts.refresh_nxt_tickers --fetch        # nextrade.co.kr 파싱 시도
    python -m batch.scripts.refresh_nxt_tickers --dry-run      # 변경사항만 출력, 저장 X
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "data" / "nxt_tickers.csv"
REQUIRED_COLS = ("stock_code", "market", "name", "tier", "source_rev")


def _read_existing() -> list[dict[str, str]]:
    if not CSV_PATH.exists():
        return []
    rows: list[dict[str, str]] = []
    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(_strip_comments(f), fieldnames=list(REQUIRED_COLS))
        for row in reader:
            if not row.get("stock_code"):
                continue
            rows.append({k: str(row.get(k, "")).strip() for k in REQUIRED_COLS})
    return rows


def _strip_comments(lines: Iterator[str]) -> Iterator[str]:
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        yield line


def _validate(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows, 1):
        code = row.get("stock_code", "")
        if not code or not code.isdigit() or len(code) != 6:
            errors.append(f"line {idx}: invalid stock_code {code!r}")
        if code in seen:
            errors.append(f"line {idx}: duplicate stock_code {code}")
        seen.add(code)
        market = row.get("market", "")
        if market not in {"KOSPI", "KOSDAQ"}:
            errors.append(f"line {idx}: invalid market {market!r} for {code}")
        try:
            int(row.get("tier", "1"))
        except ValueError:
            errors.append(f"line {idx}: invalid tier {row.get('tier')!r} for {code}")
    return errors


def _fetch_from_kiwoom() -> list[dict[str, str]]:
    """키움 ka10099 (종목정보 리스트)로 NXT 가능 종목 전수 조회.

    응답 필드 `nxtEnable='Y'` 인 종목만 필터.
    mrkt_tp='0' = KOSPI, mrkt_tp='10' = KOSDAQ.
    """
    batch_root = PROJECT_ROOT / "batch" / "runtime_source"
    if str(batch_root) not in sys.path:
        sys.path.insert(0, str(batch_root))
    from providers.kiwoom_client import KiwoomRESTClient
    from datetime import datetime

    client = KiwoomRESTClient()
    rows: list[dict[str, str]] = []

    for mrkt_tp, market_label in (("0", "KOSPI"), ("10", "KOSDAQ")):
        print(f"[nxt] fetching ka10099 mrkt_tp={mrkt_tp} ({market_label})...")
        try:
            res = client.request("/api/dostk/stkinfo", "ka10099", {"mrkt_tp": mrkt_tp})
        except Exception as exc:
            print(f"[nxt] {market_label} fetch 실패: {exc}", file=sys.stderr)
            continue
        items = res.body.get("list") if isinstance(res.body.get("list"), list) else []
        nxt_count = 0
        for item in items:
            if str(item.get("nxtEnable", "")).strip().upper() != "Y":
                continue
            code = str(item.get("code", "")).strip()
            if not code or not code.isdigit():
                continue
            rows.append({
                "stock_code": code.zfill(6),
                "market": market_label,
                "name": str(item.get("name", "")).strip(),
                "tier": "1",
                "source_rev": f"ka10099-{datetime.now().strftime('%Y%m%d')}",
            })
            nxt_count += 1
        print(f"[nxt]   {market_label}: 전체 {len(items)} 중 NXT 가능 {nxt_count}")

    return rows


# 하위 호환
_fetch_from_nextrade = _fetch_from_kiwoom


def _write_csv(rows: list[dict[str, str]]) -> None:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = (
        "# NXT (넥스트레이드) 거래 가능 종목 정적 리스트\n"
        f"# 갱신: {now_iso}\n"
        "# 소스: nextrade.co.kr/menu/marketData/menuList.do\n"
        "# 갱신 주기: 주 1회 (월요일 06:00, batch/scripts/refresh_nxt_tickers.py)\n"
        "# 컬럼: stock_code,market,name,tier,source_rev\n"
        "# tier: 1=풀서비스, 0=축소대상\n"
    )
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        f.write(header)
        writer = csv.DictWriter(f, fieldnames=list(REQUIRED_COLS), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NXT 거래가능 종목 리스트 갱신")
    parser.add_argument("--fetch", action="store_true", help="nextrade.co.kr 파싱 시도 (실험적)")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 변경사항만 출력")
    args = parser.parse_args(argv)

    existing = _read_existing()
    print(f"[nxt] current CSV entries: {len(existing)}")

    if args.fetch:
        try:
            new_rows = _fetch_from_nextrade()
        except NotImplementedError as exc:
            print(f"[nxt] WARN: {exc}", file=sys.stderr)
            return 1
        errors = _validate(new_rows)
        if errors:
            print("[nxt] validation errors:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 2
        if args.dry_run:
            added = {r["stock_code"] for r in new_rows} - {r["stock_code"] for r in existing}
            removed = {r["stock_code"] for r in existing} - {r["stock_code"] for r in new_rows}
            print(f"[nxt] dry-run: +{len(added)} / -{len(removed)}")
            return 0
        _write_csv(new_rows)
        print(f"[nxt] wrote {len(new_rows)} entries to {CSV_PATH}")
        return 0

    # 수동 모드: 기존 CSV 유효성 검사만
    errors = _validate(existing)
    if errors:
        print("[nxt] validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2
    print(f"[nxt] OK --{len(existing)} entries validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

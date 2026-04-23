"""Module G: 자동매매 루프 스케줄러 (stdlib only).

# Design Ref: Design §1.1 System Topology + §5 자동 반복 루프
# Plan §5 전체 타임라인:
#   15:30 daily_candidate_extract
#   19:30/19:40 post_close_briefing (10분 재평가)
#   19:50/19:54/19:58 trade_executor 매수 tranche
#   (익일) 08:00/02/04/05 매도 + 08:06~08:49 추격 + 09:00:30 IOC
#   09:10 daily_pnl_reconcile
#   Mon 06:00 refresh_nxt_tickers

스케줄러는 systemd(Linux)나 nssm(Windows) 같은 supervisor 아래 상주하며 매일 자동 실행.
Restart=always 권장.

Usage:
    python -m batch.runtime_source.scheduler           # 데몬 시작
    python -m batch.runtime_source.scheduler --dry-run # 시뮬레이션만
    python -m batch.runtime_source.scheduler --once    # 지금 즉시 다음 job 1회 실행
"""
from __future__ import annotations

import argparse
import logging
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEOUL_TZ = ZoneInfo("Asia/Seoul")


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s scheduler: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "runtime" / "logs" / "scheduler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("scheduler")


@dataclass
class ScheduledJob:
    name: str
    fire_time: dtime
    days: tuple[int, ...]  # 0=Mon..6=Sun
    run: Callable[[], None]
    last_run_date: str = ""


# ───── Job 구현부 ─────────────────────────────────────

def _run_module(module: str, args: list[str] = None) -> int:
    """별도 python 프로세스로 모듈 실행 (장기 실행 격리)."""
    cmd = [sys.executable, "-X", "utf8", "-m", module]
    if args:
        cmd.extend(args)
    logger.info("run: %s", " ".join(cmd))
    try:
        r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), timeout=3600, check=False)
        logger.info("exit: %s code=%d", module, r.returncode)
        return r.returncode
    except subprocess.TimeoutExpired:
        logger.error("TIMEOUT: %s", module)
        return 124


def job_15_10_batches_run_all():
    """15:10 기존 8 배치 전체 자동 실행 (LLM 포함).

    # Design Ref: Plan §5 타임라인 - 15:30 추출 전에 기존 배치 완료되도록 20분 버퍼
    # 왜 15:10? 장 마감 20분 전 시세 데이터를 쓰려는 의도.
    # ai_jongga_v2의 LLM 5회 호출이 가장 오래 걸림 (약 2-5분).

    backend.app.workers.batch_runner.runner 싱글톤을 직접 호출해서 fire-and-forget.
    실제 작업은 runner 내부 쓰레드에서 비동기 진행. 15:30 extract 시점엔 대부분 완료 상태.
    """
    try:
        # 주의: 여기서 import 해야 backend 시작 전에 scheduler.py가 eager import 안 됨
        from backend.app.workers.batch_runner import runner
        ok = runner.run_all_async(source="kiwoom")
        if ok:
            logger.info("[batches-run-all] kickoff OK (비동기, runner 내부 쓰레드에서 진행)")
        else:
            logger.warning("[batches-run-all] skipped (이미 다른 run 진행 중)")
    except Exception as exc:
        logger.exception("[batches-run-all] failed to kick off: %s", exc)


def job_15_30_extract():
    _run_module("batch.runtime_source.pipelines.daily_candidate_extract")


def job_19_30_briefing():
    _run_module("batch.runtime_source.pipelines.post_close_briefing")


def job_19_40_briefing():
    _run_module("batch.runtime_source.pipelines.post_close_briefing")


def job_19_50_buy():
    """19:50 T1 tranche. 사실 19:50/54/58 모두 TradeExecutor에서 wait_until으로 처리되므로
    19:50에 한번 trade_executor.run 호출하면 3 tranche 순차 실행.
    """
    # trade_executor 서브프로세스로 실행
    _run_module("batch.runtime_source.executor.runner_buy")


def job_08_00_sell():
    """익일 08:00 매도 시퀀스 시작. runner_sell이 08:00~09:00:30 전체 플로우 처리."""
    _run_module("batch.runtime_source.executor.runner_sell")


def job_09_10_reconcile():
    _run_module("batch.runtime_source.pipelines.daily_pnl_reconcile")


def job_mon_06_00_refresh():
    _run_module("batch.scripts.refresh_nxt_tickers")


# ───── 스케줄 정의 ─────────────────────────────────────
WEEKDAYS = (0, 1, 2, 3, 4)  # 월~금

JOBS: list[ScheduledJob] = [
    # 15:10 기존 배치 전체 실행 (AI Jongga V2의 LLM 5회 포함, 약 2-5분 소요)
    ScheduledJob("batches-run-all", dtime(15, 10), WEEKDAYS, job_15_10_batches_run_all),
    # 15:30 Top 2 추출 (15:10 run 결과 DB에서 읽음, LLM 재호출 없음)
    ScheduledJob("extract",       dtime(15, 30), WEEKDAYS, job_15_30_extract),
    # 19:30/19:40 장후 브리핑 (2종목만 — LLM 재호출해도 빠름)
    ScheduledJob("briefing-1930", dtime(19, 30), WEEKDAYS, job_19_30_briefing),
    ScheduledJob("briefing-1940", dtime(19, 40), WEEKDAYS, job_19_40_briefing),
    ScheduledJob("buy",           dtime(19, 50), WEEKDAYS, job_19_50_buy),
    ScheduledJob("sell",          dtime(8, 0),   WEEKDAYS, job_08_00_sell),
    ScheduledJob("reconcile",     dtime(9, 10),  WEEKDAYS, job_09_10_reconcile),
    ScheduledJob("refresh-nxt",   dtime(6, 0),   (0,),     job_mon_06_00_refresh),
]


# ───── 루프 ─────────────────────────────────────────

_stopping = False


def _handle_sigterm(signum, frame):
    global _stopping
    logger.info("SIGTERM received, stopping...")
    _stopping = True


def request_stop() -> None:
    """외부에서 호출 가능한 종료 요청 (FastAPI lifespan shutdown)."""
    global _stopping
    _stopping = True


def _next_fire_seconds(job: ScheduledJob, now: datetime) -> float | None:
    """다음 fire 시각까지 남은 초. 오늘 이미 지났으면 내일 같은 시각."""
    today = now.date()
    candidate = datetime.combine(today, job.fire_time, tzinfo=SEOUL_TZ)
    if candidate <= now:
        candidate += timedelta(days=1)
    # 요일 필터
    for _ in range(8):
        if candidate.weekday() in job.days:
            return (candidate - now).total_seconds()
        candidate += timedelta(days=1)
    return None


DISABLED_JOBS_PATH = PROJECT_ROOT / ".bkit" / "state" / "disabled_jobs"


def _is_job_disabled(job_name: str) -> bool:
    """사용자가 UI에서 개별 job을 off 했는지 확인 (실시간)."""
    try:
        if not DISABLED_JOBS_PATH.exists():
            return False
        disabled = {line.strip() for line in DISABLED_JOBS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()}
        return job_name in disabled
    except Exception:
        return False


def run_loop(dry_run: bool = False, embedded: bool = False):
    """embedded=True 이면 시그널 핸들러 등록 안 함 (FastAPI 쓰레드에서 호출 시)."""
    if not embedded:
        signal.signal(signal.SIGTERM, _handle_sigterm)
        try:
            signal.signal(signal.SIGINT, _handle_sigterm)
        except Exception:
            pass

    logger.info("scheduler started (dry_run=%s, embedded=%s) — %d jobs", dry_run, embedded, len(JOBS))
    for j in JOBS:
        logger.info("  %-16s %s UTC+9 days=%s", j.name, j.fire_time, j.days)

    while not _stopping:
        now = datetime.now(SEOUL_TZ)
        today_str = now.date().isoformat()

        # 매 분 fire 체크
        for job in JOBS:
            if job.last_run_date == today_str:
                continue  # 오늘 이미 실행
            if now.weekday() not in job.days:
                continue
            if now.hour == job.fire_time.hour and now.minute == job.fire_time.minute:
                # Design §9 Module G — 개별 job on/off UI 반영
                if _is_job_disabled(job.name):
                    logger.info("SKIP (disabled): %s @ %s", job.name, now.strftime("%Y-%m-%d %H:%M:%S"))
                    job.last_run_date = today_str  # 오늘 재체크 방지
                    continue
                logger.info("FIRE: %s @ %s", job.name, now.strftime("%Y-%m-%d %H:%M:%S"))
                if dry_run:
                    logger.info("  [dry-run] skip actual execution")
                else:
                    try:
                        job.run()
                    except Exception as exc:
                        logger.exception("job failed: %s: %s", job.name, exc)
                job.last_run_date = today_str

        # 30초 간격 폴링 (분 단위 정확도 확보)
        time.sleep(30)

    logger.info("scheduler stopped")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", type=str, default=None, help="즉시 실행할 job 이름")
    args = parser.parse_args()

    if args.once:
        for j in JOBS:
            if j.name == args.once:
                logger.info("once: %s", j.name)
                j.run()
                return 0
        logger.error("unknown job: %s", args.once)
        return 1

    run_loop(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

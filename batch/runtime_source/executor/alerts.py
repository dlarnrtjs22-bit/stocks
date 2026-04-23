"""Slack/이메일 알림 + 60초 취소 창.

# Design Ref: Design §5.8 + §9.1 Module G
# Plan §9.1 - Slack 알림 직전 60초 cancel 키워드 응답 수신

SLACK_WEBHOOK_URL 환경변수가 있으면 실제 Slack으로 전송.
없으면 stdout으로 로그만. (개발/테스트 편의)

cancel 응답 수신은 실제로 Slack Events API + bot token 필요. 현재는 placeholder로
.bkit/state/cancel_signal 파일 존재 여부 polling (운영자가 파일 생성하면 취소).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CANCEL_SIGNAL_PATH = PROJECT_ROOT / ".bkit" / "state" / "cancel_signal"


def notify(message: str, *, channel: str = "stocks-orders") -> None:
    """간단 알림. Slack webhook 있으면 전송, 없으면 stdout."""
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        print(f"[notify:{channel}] {message}")
        return
    try:
        data = json.dumps({"text": message, "channel": f"#{channel}"}).encode("utf-8")
        req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        print(f"[notify:FAIL:{channel}] {message} (err: {exc})")


def wait_for_cancel(message: str, wait_sec: int = 60) -> bool:
    """60초 대기하면서 취소 신호 감지.
    반환: True = 진행 OK, False = 사용자가 취소 요청

    취소 방법:
      1. .bkit/state/cancel_signal 파일 생성 (touch)
      2. (선택) Slack 봇 설치 시 reply로 'cancel' 입력
    """
    notify(f"{message}\n `touch .bkit/state/cancel_signal` 또는 'cancel' 입력 시 60초 내 중단")
    deadline = time.time() + max(wait_sec, 1)
    CANCEL_SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 기존 신호가 있으면 삭제 (이번 창용)
    if CANCEL_SIGNAL_PATH.exists():
        try:
            CANCEL_SIGNAL_PATH.unlink()
        except Exception:
            pass
    while time.time() < deadline:
        if CANCEL_SIGNAL_PATH.exists():
            try:
                CANCEL_SIGNAL_PATH.unlink()
            except Exception:
                pass
            return False  # cancel
        time.sleep(1)
    return True

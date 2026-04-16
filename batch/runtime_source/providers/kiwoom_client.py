from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import websockets


REST_BASE_URL = "https://api.kiwoom.com"
WS_BASE_URL = "wss://api.kiwoom.com:10000/api/dostk/websocket"
TOKEN_PATH = "/oauth2/token"
APPKEY_FILE_NAME = "58416417_appkey.txt"
SECRETKEY_FILE_NAME = "58416417_secretkey.txt"


class KiwoomAPIError(RuntimeError):
    pass


@dataclass(slots=True)
class KiwoomResponse:
    body: dict[str, Any]
    headers: dict[str, str]


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def effective_venue(now_epoch: float | None = None) -> tuple[str, str]:
    ts = time.localtime(now_epoch or time.time())
    hhmm = ts.tm_hour * 100 + ts.tm_min
    if hhmm >= 1540:
        return "NXT", "2"
    return "KRX", "1"


def venue_stock_code(ticker: str, venue: str) -> str:
    base = str(ticker or "").strip().upper()
    if not base:
        return ""
    if venue == "NXT" and not base.endswith("_NX"):
        return f"{base}_NX"
    return base


class KiwoomRESTClient:
    def __init__(self) -> None:
        self._project_root = project_root()
        self._appkey = self._read_secret(APPKEY_FILE_NAME)
        self._secretkey = self._read_secret(SECRETKEY_FILE_NAME)
        self._token = ""
        self._expires_at = 0.0
        self._session = requests.Session()
        self._last_request_ts = 0.0
        self._min_interval_sec = 0.22
        self._max_retries = 5

    def _read_secret(self, file_name: str) -> str:
        path = self._project_root / file_name
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            raise KiwoomAPIError(f"{file_name} is empty")
        return value

    def access_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token

        response = self._session.post(
            f"{REST_BASE_URL}{TOKEN_PATH}",
            json={
                "grant_type": "client_credentials",
                "appkey": self._appkey,
                "secretkey": self._secretkey,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        token = str(data.get("token", "")).strip()
        if not token:
            raise KiwoomAPIError(str(data.get("return_msg", "kiwoom token missing")))
        self._token = token
        self._expires_at = time.time() + 60 * 50
        return token

    def request(self, path: str, api_id: str, payload: dict[str, Any], *, cont_yn: str = "N", next_key: str = "") -> KiwoomResponse:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self.access_token()}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": api_id,
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            sleep_for = self._min_interval_sec - (time.time() - self._last_request_ts)
            if sleep_for > 0:
                time.sleep(sleep_for)

            response = self._session.post(
                f"{REST_BASE_URL}{path}",
                headers=headers,
                json=payload,
                timeout=30,
            )
            self._last_request_ts = time.time()

            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                wait_sec = float(retry_after) if retry_after else self._min_interval_sec * (2 ** attempt)
                time.sleep(max(wait_sec, self._min_interval_sec))
                last_error = KiwoomAPIError(f"rate limited: {api_id}")
                continue

            response.raise_for_status()
            body = response.json()
            return_code = body.get("return_code")
            if return_code is not None and str(return_code).strip() not in {"", "0"}:
                message = str(body.get("return_msg", "") or response.text[:200])
                raise KiwoomAPIError(message)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return KiwoomResponse(body=body, headers=response_headers)

        raise last_error or KiwoomAPIError(f"kiwoom request failed after retries: {api_id}")

    def paginate(self, path: str, api_id: str, payload: dict[str, Any], *, max_pages: int = 10) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        cont_yn = "N"
        next_key = ""
        for _ in range(max_pages):
            result = self.request(path, api_id, payload, cont_yn=cont_yn, next_key=next_key)
            pages.append(result.body)
            cont_yn = str(result.headers.get("cont-yn", "N") or "N").upper()
            next_key = str(result.headers.get("next-key", "") or "")
            if cont_yn != "Y" or not next_key:
                break
        return pages


class KiwoomWebSocketClient:
    def __init__(self, rest_client: KiwoomRESTClient | None = None) -> None:
        self._rest = rest_client or KiwoomRESTClient()

    async def request_once(self, payload: dict[str, Any], *, expect_trnm: str | None = None, timeout_sec: int = 15) -> dict[str, Any]:
        async with websockets.connect(WS_BASE_URL, max_size=2**22) as ws:
            await ws.send(json.dumps({"trnm": "LOGIN", "token": self._rest.access_token()}))
            login_response = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout_sec))
            if int(login_response.get("return_code", 1) or 1) != 0:
                raise KiwoomAPIError(str(login_response.get("return_msg", "websocket login failed")))

            await ws.send(json.dumps(payload))
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout_sec))
                if message.get("trnm") == "LOGIN":
                    continue
                if expect_trnm and message.get("trnm") not in {expect_trnm, "REAL"}:
                    continue
                return message

    def request(self, payload: dict[str, Any], *, expect_trnm: str | None = None, timeout_sec: int = 15) -> dict[str, Any]:
        return asyncio.run(self.request_once(payload, expect_trnm=expect_trnm, timeout_sec=timeout_sec))

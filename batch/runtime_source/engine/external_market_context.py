from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


YAHOO_SPARK_URL = "https://query1.finance.yahoo.com/v7/finance/spark"
SESSION = requests.Session()

_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"fetched_at": 0.0, "value": None}


@dataclass(frozen=True)
class MarketSymbolSpec:
    key: str
    symbol: str
    label: str
    proxy: bool = False
    proxy_for: str = ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _iso_from_timestamp(value: Any) -> str | None:
    try:
        ts = int(value)
    except Exception:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat()


def _latest_two(values: List[Any]) -> tuple[Optional[float], Optional[float]]:
    cleaned = [_safe_float(v, float("nan")) for v in values]
    filtered = [v for v in cleaned if v == v]
    if not filtered:
        return None, None
    latest = filtered[-1]
    previous = filtered[-2] if len(filtered) >= 2 else None
    return latest, previous


def _build_symbol_specs() -> List[MarketSymbolSpec]:
    custom_night_symbol = str(os.getenv("KOSPI_NIGHT_SYMBOL", "") or "").strip()
    custom_night_label = str(os.getenv("KOSPI_NIGHT_LABEL", "KOSPI Night Futures") or "KOSPI Night Futures").strip()

    if custom_night_symbol:
        night_spec = MarketSymbolSpec(
            key="kospi_night",
            symbol=custom_night_symbol,
            label=custom_night_label,
            proxy=False,
        )
    else:
        night_spec = MarketSymbolSpec(
            key="kospi_night",
            symbol="^KS200",
            label="KOSPI200 Night Proxy",
            proxy=True,
            proxy_for="KOSPI Night Futures",
        )

    return [
        night_spec,
        MarketSymbolSpec(key="kospi", symbol="^KS11", label="KOSPI"),
        MarketSymbolSpec(key="kosdaq", symbol="^KQ11", label="KOSDAQ"),
        MarketSymbolSpec(key="nasdaq_futures", symbol="NQ=F", label="Nasdaq Futures"),
        MarketSymbolSpec(key="sp500_futures", symbol="ES=F", label="S&P Futures"),
        MarketSymbolSpec(key="usdkrw", symbol="KRW=X", label="USD/KRW"),
    ]


def _snapshot_from_response(spec: MarketSymbolSpec, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    meta = response.get("meta") if isinstance(response.get("meta"), dict) else {}
    indicators = response.get("indicators") if isinstance(response.get("indicators"), dict) else {}
    quote_list = indicators.get("quote") if isinstance(indicators.get("quote"), list) else []
    quote = quote_list[0] if quote_list and isinstance(quote_list[0], dict) else {}
    closes = quote.get("close") if isinstance(quote.get("close"), list) else []
    latest_close, previous_close = _latest_two(list(closes))

    price = _safe_float(meta.get("regularMarketPrice"), latest_close or 0.0)
    prev_close = _safe_float(meta.get("chartPreviousClose"), previous_close or 0.0)
    if price <= 0:
        price = latest_close or 0.0
    if prev_close <= 0:
        prev_close = previous_close or 0.0
    if price <= 0 or prev_close <= 0:
        return None

    return {
        "label": spec.label,
        "symbol": spec.symbol,
        "price": round(price, 4),
        "previous_close": round(prev_close, 4),
        "change_pct": round((price - prev_close) / prev_close * 100.0, 2),
        "exchange": str(meta.get("exchangeName", "") or ""),
        "instrument_type": str(meta.get("instrumentType", "") or ""),
        "market_state": str(meta.get("marketState", "") or ""),
        "market_time": _iso_from_timestamp(meta.get("regularMarketTime")),
        "source": "yahoo_spark",
        "proxy": bool(spec.proxy),
        "proxy_for": spec.proxy_for,
    }


def _fetch_spark_snapshots(specs: List[MarketSymbolSpec], timeout_sec: int) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
    snapshots: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    if not specs:
        return snapshots, errors

    try:
        resp = SESSION.get(
            YAHOO_SPARK_URL,
            params={
                "symbols": ",".join(spec.symbol for spec in specs),
                "range": "5d",
                "interval": "1d",
                "includeTimestamps": "true",
                "includePrePost": "true",
            },
            timeout=timeout_sec,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        payload = resp.json()
        results = payload.get("spark", {}).get("result", []) if isinstance(payload, dict) else []
        spec_by_symbol = {spec.symbol: spec for spec in specs}

        for item in results if isinstance(results, list) else []:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol", "") or "")
            spec = spec_by_symbol.get(symbol)
            if spec is None:
                continue
            responses = item.get("response") if isinstance(item.get("response"), list) else []
            response = responses[0] if responses and isinstance(responses[0], dict) else {}
            snapshot = _snapshot_from_response(spec, response)
            if snapshot:
                snapshots[spec.key] = snapshot
    except Exception as exc:
        errors.append(f"spark: {exc}")

    return snapshots, errors


def _append_component(
    components: List[Dict[str, Any]],
    snapshot: Dict[str, Any],
    *,
    delta: float,
    reason: str,
) -> None:
    components.append(
        {
            "key": str(snapshot.get("symbol", "") or ""),
            "label": str(snapshot.get("label", "") or ""),
            "change_pct": round(_safe_float(snapshot.get("change_pct"), 0.0), 2),
            "delta": round(delta, 2),
            "reason": reason,
            "proxy": bool(snapshot.get("proxy", False)),
            "source": str(snapshot.get("source", "") or ""),
        }
    )


def _evaluate_market_context(signals: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    risk_score = 50.0
    evidence: List[str] = []
    components: List[Dict[str, Any]] = []

    night = signals.get("kospi_night") or {}
    night_change = _safe_float(night.get("change_pct"), 0.0)
    night_label = str(night.get("proxy_for") or night.get("label") or "KOSPI Night")
    night_suffix = "(proxy)" if bool(night.get("proxy", False)) else ""
    if night_change <= -1.0:
        risk_score -= 14
        reason = f"{night_label}{night_suffix} {night_change:+.2f}%로 국내 개장 전 위험 신호가 강합니다."
        evidence.append(reason)
        _append_component(components, night, delta=-14, reason=reason)
    elif night_change <= -0.5:
        risk_score -= 8
        reason = f"{night_label}{night_suffix} {night_change:+.2f}%로 국내 선행 흐름이 약합니다."
        evidence.append(reason)
        _append_component(components, night, delta=-8, reason=reason)
    elif night_change >= 0.8:
        risk_score += 6
        reason = f"{night_label}{night_suffix} {night_change:+.2f}%로 국내 선행 흐름이 우호적입니다."
        evidence.append(reason)
        _append_component(components, night, delta=6, reason=reason)

    nq = signals.get("nasdaq_futures") or {}
    nq_change = _safe_float(nq.get("change_pct"), 0.0)
    if nq_change <= -1.0:
        risk_score -= 16
        reason = f"Nasdaq futures {nq_change:+.2f}%로 성장주 위험 선호가 약합니다."
        evidence.append(reason)
        _append_component(components, nq, delta=-16, reason=reason)
    elif nq_change <= -0.5:
        risk_score -= 9
        reason = f"Nasdaq futures {nq_change:+.2f}%로 미국 기술주 선물이 약세입니다."
        evidence.append(reason)
        _append_component(components, nq, delta=-9, reason=reason)
    elif nq_change >= 0.6:
        risk_score += 8
        reason = f"Nasdaq futures {nq_change:+.2f}%로 글로벌 위험 선호가 우호적입니다."
        evidence.append(reason)
        _append_component(components, nq, delta=8, reason=reason)

    es = signals.get("sp500_futures") or {}
    es_change = _safe_float(es.get("change_pct"), 0.0)
    if es_change <= -0.8:
        risk_score -= 10
        reason = f"S&P futures {es_change:+.2f}%로 미국 지수 전반이 약합니다."
        evidence.append(reason)
        _append_component(components, es, delta=-10, reason=reason)
    elif es_change >= 0.6:
        risk_score += 6
        reason = f"S&P futures {es_change:+.2f}%로 미국 지수 전반이 받쳐줍니다."
        evidence.append(reason)
        _append_component(components, es, delta=6, reason=reason)

    kospi = signals.get("kospi") or {}
    kospi_change = _safe_float(kospi.get("change_pct"), 0.0)
    if kospi_change <= -1.0:
        risk_score -= 8
        reason = f"KOSPI {kospi_change:+.2f}%로 국내 대형주 흐름이 약합니다."
        evidence.append(reason)
        _append_component(components, kospi, delta=-8, reason=reason)
    elif kospi_change >= 1.0:
        risk_score += 5
        reason = f"KOSPI {kospi_change:+.2f}%로 국내 대형주 흐름이 안정적입니다."
        evidence.append(reason)
        _append_component(components, kospi, delta=5, reason=reason)

    kosdaq = signals.get("kosdaq") or {}
    kosdaq_change = _safe_float(kosdaq.get("change_pct"), 0.0)
    if kosdaq_change <= -1.2:
        risk_score -= 7
        reason = f"KOSDAQ {kosdaq_change:+.2f}%로 중소형 성장주 심리가 위축돼 있습니다."
        evidence.append(reason)
        _append_component(components, kosdaq, delta=-7, reason=reason)
    elif kosdaq_change >= 1.0:
        risk_score += 4
        reason = f"KOSDAQ {kosdaq_change:+.2f}%로 성장주 심리가 회복 중입니다."
        evidence.append(reason)
        _append_component(components, kosdaq, delta=4, reason=reason)

    usdkrw = signals.get("usdkrw") or {}
    usdkrw_price = _safe_float(usdkrw.get("price"), 0.0)
    usdkrw_change = _safe_float(usdkrw.get("change_pct"), 0.0)
    if usdkrw_price >= 1450 or usdkrw_change >= 0.7:
        risk_score -= 12
        reason = f"USD/KRW {usdkrw_price:,.1f}원({usdkrw_change:+.2f}%)으로 환율 부담이 큽니다."
        evidence.append(reason)
        _append_component(components, usdkrw, delta=-12, reason=reason)
    elif usdkrw_price >= 1400 or usdkrw_change >= 0.3:
        risk_score -= 6
        reason = f"USD/KRW {usdkrw_price:,.1f}원으로 외국인 수급 부담이 남아 있습니다."
        evidence.append(reason)
        _append_component(components, usdkrw, delta=-6, reason=reason)
    elif 0 < usdkrw_price <= 1360 and usdkrw_change <= -0.2:
        risk_score += 3
        reason = f"USD/KRW {usdkrw_price:,.1f}원({usdkrw_change:+.2f}%)으로 환율 부담이 완화되고 있습니다."
        evidence.append(reason)
        _append_component(components, usdkrw, delta=3, reason=reason)

    if night_change <= -0.5 and nq_change <= -0.5:
        risk_score -= 4
        reason = "국내 선행 지표와 미국 기술주 선물이 동반 약세라 갭하락 리스크가 커집니다."
        evidence.append(reason)
        components.append({"key": "cross_market", "label": "Cross Market", "delta": -4.0, "reason": reason})
    elif night_change >= 0.5 and nq_change >= 0.5:
        risk_score += 3
        reason = "국내 선행 지표와 미국 기술주 선물이 함께 강해 위험 선호가 살아 있습니다."
        evidence.append(reason)
        components.append({"key": "cross_market", "label": "Cross Market", "delta": 3.0, "reason": reason})

    risk_score = max(0.0, min(100.0, risk_score))
    if risk_score >= 62:
        status = "RISK_ON"
        summary = "해외/선행 시장 흐름이 우호적입니다. 강한 종목은 선별 진입이 가능합니다."
    elif risk_score >= 48:
        status = "CAUTION"
        summary = "해외/선행 시장 흐름이 혼조입니다. 상위 등급 위주로 보수적으로 접근해야 합니다."
    else:
        status = "RISK_OFF"
        summary = "해외/선행 시장 흐름이 약세입니다. 신규 진입은 매우 보수적으로 봐야 합니다."

    return {
        "status": status,
        "risk_score": round(risk_score, 2),
        "summary": summary,
        "evidence": evidence[:5],
        "components": components,
        "signals": signals,
        "source": "yahoo_spark",
        "proxy_used": any(bool(v.get("proxy", False)) for v in signals.values()),
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }


def fetch_external_market_context(timeout_sec: int = 6) -> Dict[str, Any]:
    specs = _build_symbol_specs()
    signals, errors = _fetch_spark_snapshots(specs, timeout_sec)

    if not signals:
        return {
            "status": "UNAVAILABLE",
            "risk_score": 50.0,
            "summary": "외부 시장 컨텍스트를 가져오지 못해 내부 시황만 사용합니다.",
            "evidence": [],
            "components": [],
            "signals": {},
            "source": "unavailable",
            "errors": errors[:4],
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        }

    evaluated = _evaluate_market_context(signals)
    if errors:
        evaluated["errors"] = errors[:4]
    return evaluated


def get_external_market_context(*, force_refresh: bool = False, max_age_sec: int = 300) -> Dict[str, Any]:
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get("value")
        fetched_at = float(_CACHE.get("fetched_at") or 0.0)
        if (not force_refresh) and isinstance(cached, dict) and cached and (now - fetched_at) < max_age_sec:
            return dict(cached)

    fresh = fetch_external_market_context()
    with _CACHE_LOCK:
        _CACHE["value"] = dict(fresh)
        _CACHE["fetched_at"] = now
    return fresh

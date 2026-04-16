from __future__ import annotations

ETF_NAME_PREFIXES = (
    "KODEX",
    "TIGER",
    "KOSEF",
    "KINDEX",
    "KBSTAR",
    "ARIRANG",
    "ACE ",
    "ACE",
    "SOL",
    "HANARO",
    "TIMEFOLIO",
    "RISE",
    "PLUS",
    "TREX",
    "SMART",
    "FOCUS",
    "TRUE",
    "QV",
    "1Q",
    "WOORI",
)


def is_etf_or_etn_name(name: str) -> bool:
    normalized = str(name or "").strip().upper()
    if not normalized:
        return False
    if "ETF" in normalized or "ETN" in normalized:
        return True
    return any(normalized.startswith(prefix) for prefix in ETF_NAME_PREFIXES)

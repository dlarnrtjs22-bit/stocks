from __future__ import annotations

from collections import defaultdict
from typing import Iterable


THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "반도체": ("반도체", "hbm", "d램", "dram", "낸드", "후공정", "패키징", "칩", "파운드리", "메모리", "semicon"),
    "2차전지": ("배터리", "2차전지", "리튬", "양극재", "음극재", "전해질", "ess", "battery", "sdi"),
    "바이오": ("바이오", "제약", "신약", "임상", "항암", "세포", "pharm", "bio", "의약"),
    "방산": ("방산", "미사일", "전투기", "탄약", "레이더", "국방", "방위", "무기"),
    "조선": ("조선", "lng선", "해양플랜트", "선박", "ship", "해운"),
    "자동차": ("자동차", "전기차", "ev", "차량", "완성차", "모빌리티", "autonomous"),
    "금융": ("은행", "증권", "보험", "카드", "금융", "bank", "capital", "asset"),
    "AI/플랫폼": ("ai", "인공지능", "클라우드", "플랫폼", "데이터센터", "saas", "로봇", "robot", "llm"),
    "게임/콘텐츠": ("게임", "엔터", "콘텐츠", "drama", "music", "ott", "webtoon"),
    "에너지": ("에너지", "태양광", "풍력", "원전", "수소", "정유", "가스", "electricity"),
    "철강/소재": ("철강", "구리", "니켈", "희토류", "소재", "metal", "합금"),
    "유통/소비재": ("화장품", "식품", "유통", "면세", "소비", "리테일", "retail"),
    "통신": ("통신", "5g", "네트워크", "telecom"),
}


def _normalize_text(value: str) -> str:
    text = str(value or "").strip().lower()
    text = " ".join(text.split())
    return "".join(ch for ch in text if ch.isalnum() or ("가" <= ch <= "힣"))


def infer_theme(name: str, texts: Iterable[str] | None = None, fallback: str = "General") -> str:
    score_map: dict[str, int] = defaultdict(int)
    candidates = [_normalize_text(name)]
    if texts is not None:
        candidates.extend(_normalize_text(text) for text in texts if str(text).strip())

    for candidate in candidates:
        if not candidate:
            continue
        for theme, keywords in THEME_KEYWORDS.items():
            for keyword in keywords:
                token = _normalize_text(keyword)
                if token and token in candidate:
                    score_map[theme] += 1

    if not score_map:
        return str(fallback or "General")
    return max(score_map.items(), key=lambda item: (item[1], item[0]))[0]

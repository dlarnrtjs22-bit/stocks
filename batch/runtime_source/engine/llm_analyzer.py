from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .decision_policy import decide_trade_opinion
from .news_window import describe_news_window
from .scoring_constants import BUY_SCORE_THRESHOLD, TOTAL_RULE_SCORE_MAX

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None

if load_dotenv:
    load_dotenv()


def _clamp_score(value: Any, default: int = 1) -> int:
    try:
        return max(0, min(3, int(value)))
    except Exception:
        return max(0, min(3, int(default)))


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}

    if "```" in raw:
        raw = re.sub(r"```json|```", "", raw).strip()

    if not (raw.startswith("{") and raw.endswith("}")):
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)

    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


DEFAULT_CODEX_MODEL = "gpt-5.4"


def _format_trade_levels(metrics: Dict[str, Any]) -> str:
    entry_price = _to_float(metrics.get("entry_price", 0.0))
    target_price = _to_float(metrics.get("target_price", 0.0))
    stop_price = _to_float(metrics.get("stop_price", 0.0))
    return (
        f"목표가 : {target_price:,.0f}\n"
        f"손절가 : {stop_price:,.0f}\n"
        f"기준가 : {entry_price:,.0f}"
    )


def _fresh_news_label(metrics: Dict[str, Any]) -> str:
    value = str(metrics.get("news_window_label", "") or "").strip()
    return value or describe_news_window(datetime.now().date())


class LLMProviderError(RuntimeError):
    pass


class LLMAnalyzer:
    """
    Provider priority:
    1) Codex (project-local `chatgpt.py`) - read-only import
    2) Gemini (optional)
    3) deterministic default score
    """

    def __init__(self, api_key: str | None = None):
        self._project_root = Path(__file__).resolve().parents[3]
        self._runtime_root = self._project_root / "batch" / "runtime_source"
        self.provider = str(os.getenv("LLM_PROVIDER", "codex")).strip().lower()
        self.strict_provider = str(os.getenv("LLM_STRICT_PROVIDER", "1")).strip().lower() not in {"0", "false", "no"}
        self.default_news_score = _clamp_score(os.getenv("NEWS_DEFAULT_SCORE", 1), default=1)
        self.timeout_sec = int(os.getenv("LLM_TIMEOUT_SEC", "120") or 120)

        self.model = None
        effort = str(os.getenv("CODEX_REASONING_EFFORT", "high")).strip().lower() or "high"
        if effort not in {"low", "medium", "high"}:
            effort = "high"
        self.reasoning_effort = effort

        self._codex_sender = None
        self._codex_transport = "none"
        self._codex_init_error = ""
        self._codex_model = DEFAULT_CODEX_MODEL
        self._openai_api_key = str(os.getenv("OPENAI_API_KEY", "")).strip()
        self._openai_base_url = str(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).strip() or "https://api.openai.com/v1"

        # fallback provider
        self._gemini_model = None
        self._gemini_api_key = api_key or os.getenv("GOOGLE_API_KEY")

        if self.provider == "codex":
            self._init_codex_sender()
        elif self.provider == "gemini":
            self._init_gemini_model()

        if self.provider == "off" and self.strict_provider:
            raise LLMProviderError("LLM_PROVIDER=off is disabled in strict mode")

        if self.strict_provider and (not self.is_ready()):
            raise LLMProviderError(self.get_not_ready_reason())

    def is_ready(self) -> bool:
        if self.provider == "codex":
            return bool(self.model) and (self._codex_sender is not None or self._codex_transport == "responses_api")
        if self.provider == "gemini":
            return bool(self.model) and (self._gemini_model is not None)
        if self.provider == "off":
            return False
        return bool(self.model)

    def get_not_ready_reason(self) -> str:
        if self.provider == "codex":
            detail = self._codex_init_error or "Codex sender unavailable"
            return (
                "Codex provider is required but not ready. "
                f"{detail}. "
                f"Expected project-local auth at {self._project_root / 'chatgptOauthKey.json'}, "
                "or set OPENAI_API_KEY for direct Responses API transport."
            )
        if self.provider == "gemini":
            return "Gemini provider is required but not ready. Check GOOGLE_API_KEY and GEMINI_MODEL."
        if self.provider == "off":
            return "LLM provider is off"
        return "LLM provider is not ready"

    def _candidate_codex_dirs(self) -> List[Path]:
        candidates: List[Path] = [
            self._project_root,
            self._runtime_root,
        ]

        dedup: List[Path] = []
        seen = set()
        for p in candidates:
            key = str(p.resolve()) if p.exists() else str(p)
            if key in seen:
                continue
            seen.add(key)
            dedup.append(p)
        return dedup

    def _resolve_codex_module_path(self) -> Optional[Path]:
        checked: List[str] = []
        for base in self._candidate_codex_dirs():
            module_path = base / "chatgpt.py"
            checked.append(str(module_path))
            if module_path.exists():
                return module_path
        self._codex_init_error = "chatgpt.py not found. checked: " + ", ".join(checked)
        return None

    def _init_codex_sender(self) -> None:
        module_path = self._resolve_codex_module_path()
        if module_path is None:
            if self._openai_api_key:
                self._codex_transport = "responses_api"
                self.model = self._codex_model
                return
            return

        try:
            spec = importlib.util.spec_from_file_location("external_codex_chatgpt", str(module_path))
            if not spec or not spec.loader:
                self._codex_init_error = f"failed to load module spec: {module_path}"
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sender = getattr(module, "send_codex_message", None)
            if sender is None:
                self._codex_init_error = "send_codex_message not found in chatgpt.py"
                return

            token_file = getattr(module, "TOKEN_FILE", None)
            if token_file is not None:
                token_path = Path(token_file)
                if not token_path.exists():
                    if self._openai_api_key:
                        self._codex_sender = None
                        self._codex_transport = "responses_api"
                        self.model = self._codex_model
                        self._codex_init_error = (
                            f"token file not found: {token_path}; switched to OPENAI_API_KEY transport"
                        )
                        return
                    self._codex_init_error = f"token file not found: {token_path}"
                    self._codex_sender = None
                    self._codex_transport = "none"
                    self.model = None
                    return

            self._codex_sender = sender
            self._codex_transport = "external_sender"
            self.model = self._codex_model
            self._codex_init_error = ""
        except Exception:
            self._codex_sender = None
            self.model = None
            self._codex_transport = "none"
            self._codex_init_error = f"failed to import chatgpt.py: {module_path}"

    def _init_gemini_model(self) -> None:
        if not self._gemini_api_key:
            return
        try:
            genai = importlib.import_module("google.generativeai")
            configure = getattr(genai, "configure", None)
            model_cls = getattr(genai, "GenerativeModel", None)
            if (not callable(configure)) or (model_cls is None):
                return

            configure(api_key=self._gemini_api_key)
            model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
            self._gemini_model = model_cls(model_name)
            self.model = model_name
        except Exception:
            self._gemini_model = None
            self.model = None

    def _default_result(self, *, reason: str, status: str, stock_name: str) -> Dict[str, Any]:
        return {
            "score": int(self.default_news_score),
            "reason": reason,
            "status": status,
            "provider": self.provider,
            "model": str(self.model or ""),
            "reasoning_effort": self.reasoning_effort,
            "meta": {
                "status": status,
                "provider": self.provider,
                "model": str(self.model or ""),
                "reasoning_effort": self.reasoning_effort,
                "stock": stock_name,
                "material_strength": 0.0,
                "attention_score": 0.0,
                "novelty_score": 0.0,
                "entity_confidence": 0.0,
                "category": "",
                "tone": "mixed",
            },
        }

    def _no_news_result(self, *, stock_name: str) -> Dict[str, Any]:
        return {
            "score": 0,
            "reason": "당일 및 전일 장마감 이후 종목 직접 관련 뉴스가 없어 뉴스 점수 0점을 적용했습니다.",
            "status": "NO_NEWS",
            "provider": self.provider,
            "model": str(self.model or ""),
            "reasoning_effort": self.reasoning_effort,
            "meta": {
                "status": "NO_NEWS",
                "provider": self.provider,
                "model": str(self.model or ""),
                "reasoning_effort": self.reasoning_effort,
                "stock": stock_name,
                "material_strength": 0.0,
                "attention_score": 0.0,
                "novelty_score": 0.0,
                "entity_confidence": 0.0,
                "category": "",
                "tone": "mixed",
            },
        }

    def _build_rule_based_summary(
        self,
        *,
        stock_name: str,
        total_score: int,
        rule_scores: Dict[str, Any],
        metrics: Dict[str, Any],
        news_items: List[Dict],
        reason: str,
    ) -> Dict[str, Any]:
        market_context = metrics.get("market_context") if isinstance(metrics.get("market_context"), dict) else {}
        program_context = metrics.get("program_context") if isinstance(metrics.get("program_context"), dict) else {}
        external_market_context = (
            metrics.get("external_market_context")
            if isinstance(metrics.get("external_market_context"), dict)
            else {}
        )
        market_policy = metrics.get("market_policy") if isinstance(metrics.get("market_policy"), dict) else None
        decision = decide_trade_opinion(
            grade=metrics.get("base_grade", metrics.get("grade")),
            total_score=total_score,
            market_context=market_context,
            program_context=program_context,
            external_market_context=external_market_context,
            grade_policy=market_policy,
            fresh_news_count=metrics.get("fresh_news_count"),
        )
        opinion = str(decision.get("opinion", "매도") or "매도")

        breakdown = {
            "news": _to_int(rule_scores.get("news", 0)),
            "supply": _to_int(rule_scores.get("supply", 0)),
            "volume": _to_int(rule_scores.get("volume", 0)),
            "chart": _to_int(rule_scores.get("chart", 0)),
            "candle": _to_int(rule_scores.get("candle", 0)),
            "consolidation": _to_int(rule_scores.get("consolidation", 0)),
            "market": _to_int(rule_scores.get("market", 0)),
            "program": _to_int(rule_scores.get("program", 0)),
            "sector": _to_int(rule_scores.get("sector", 0)),
            "leader": _to_int(rule_scores.get("leader", 0)),
            "intraday": _to_int(rule_scores.get("intraday", 0)),
            "news_attention": _to_int(rule_scores.get("news_attention", 0)),
        }

        evidence: List[str] = []
        top_titles = [str(n.get("title", "") or "").strip() for n in news_items[:2] if str(n.get("title", "") or "").strip()]
        if top_titles:
            evidence.append(f"최근 뉴스 핵심: {' / '.join(top_titles)}")
        else:
            evidence.append(f"{_fresh_news_label(metrics)} 구간에 종목 직접 관련 뉴스가 없어 재료 확신이 낮습니다.")

        if breakdown["supply"] >= 1:
            evidence.append("수급 점수가 양호해 외국인/기관 흐름이 일부 우호적입니다.")
        else:
            evidence.append("수급 점수가 낮아 매수 주체의 확신이 약합니다.")

        if breakdown["chart"] >= 2:
            evidence.append("차트 점수는 돌파/추세 측면에서 긍정 신호를 시사합니다.")
        elif breakdown["chart"] <= 0:
            evidence.append("차트 점수가 낮아 추세 신뢰도가 부족합니다.")

        if breakdown["market"] >= 1:
            evidence.append("시장 시황이 우호적이라 종가배팅 추종 매매에 부담이 덜합니다.")
        if breakdown["program"] >= 1:
            evidence.append("프로그램 수급도 플러스여서 마감 수급에 보조 신호가 있습니다.")
        if breakdown["sector"] >= 1:
            evidence.append("주도 섹터 흐름이 우호적이어서 시장 중심주의 조건에 가깝습니다.")
        if breakdown["leader"] >= 1:
            evidence.append("동일 섹터 내 선도주로 해석할 여지가 있어 소외주 리스크가 낮습니다.")
        if breakdown["intraday"] >= 1:
            evidence.append("막판 체결/호가 흐름이 지지돼 장 마감 압력이 살아 있습니다.")
        if breakdown["news_attention"] >= 1:
            evidence.append("뉴스 화제성과 매체 확산도가 있어 시장의 주목도를 받는 재료에 가깝습니다.")

        change_pct = _to_float(metrics.get("change_pct", 0.0))
        trading_value = _to_float(metrics.get("trading_value", 0.0))
        evidence.append(
            f"당일 등락률 {change_pct:+.2f}%, 거래대금 {trading_value / 100_000_000:,.0f}억원 수준입니다."
        )

        score_text = (
            f"뉴스 {breakdown['news']}/3, 수급 {breakdown['supply']}/2, 거래량 {breakdown['volume']}/3, "
            f"차트 {breakdown['chart']}/2, 캔들 {breakdown['candle']}/1, 기간조정 {breakdown['consolidation']}/1, "
            f"시황 {breakdown['market']}/1, 프로그램 {breakdown['program']}/1, 섹터 {breakdown['sector']}/2, "
            f"대장 {breakdown['leader']}/2, 장중압력 {breakdown['intraday']}/2, 화제성 {breakdown['news_attention']}/2"
        )
        reason_prefix = f"{reason.strip()} " if str(reason).strip() else ""
        decision_text = " ".join(str(x).strip() for x in decision.get("reasons", []) if str(x).strip())
        summary = (
            f"{reason_prefix}규칙 점수 {int(total_score)}/{TOTAL_RULE_SCORE_MAX}({score_text}) 기준 {opinion} 의견입니다. "
            f"{decision_text} {evidence[0]} {evidence[1]} {evidence[-1]}\n{_format_trade_levels(metrics)}"
        )

        return {
            "opinion": opinion,
            "summary": summary,
            "evidence": evidence,
            "breakdown": breakdown,
            "decision": decision,
        }

    def build_rule_based_overall(
        self,
        *,
        stock_name: str,
        rule_scores: Dict[str, Any],
        metrics: Dict[str, Any],
        news_items: List[Dict],
        status: str = "FALLBACK",
        reason: str = "",
    ) -> Dict[str, Any]:
        total_score = _to_int(rule_scores.get("total", 0))
        built = self._build_rule_based_summary(
            stock_name=stock_name,
            total_score=total_score,
            rule_scores=rule_scores,
            metrics=metrics,
            news_items=news_items,
            reason=reason,
        )
        return {
            "opinion": built["opinion"],
            "summary": built["summary"],
            "status": status,
            "provider": self.provider,
            "model": str(self.model or ""),
            "reasoning_effort": self.reasoning_effort,
            "meta": {
                "status": status,
                "provider": self.provider,
                "model": str(self.model or ""),
                "reasoning_effort": self.reasoning_effort,
                "stock": stock_name,
                "total_score": total_score,
                "breakdown": built["breakdown"],
                "evidence": built["evidence"],
                "decision": built["decision"],
            },
        }

    def _default_overall(
        self,
        *,
        stock_name: str,
        total_score: int = 0,
        reason: str = "",
        rule_scores: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        news_items: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        rs = dict(rule_scores or {"total": total_score})
        rs.setdefault("total", int(total_score))
        return self.build_rule_based_overall(
            stock_name=stock_name,
            rule_scores=rs,
            metrics=dict(metrics or {}),
            news_items=list(news_items or []),
            status="FALLBACK",
            reason=reason,
        )

    async def analyze_news_sentiment(self, stock_name: str, news_items: List[Dict]) -> Dict[str, Any]:
        if not news_items:
            return self._no_news_result(stock_name=stock_name)

        if self.provider == "codex" and self._codex_sender:
            return await self._analyze_with_codex(stock_name, news_items)

        if self.provider == "gemini" and self._gemini_model:
            return await self._analyze_with_gemini(stock_name, news_items)

        return self._default_result(
            reason="AI 모델 초기화에 실패하여 기본점수 1점을 적용했습니다.",
            status="NO_MODEL",
            stock_name=stock_name,
        )

    async def analyze_overall_decision(
        self,
        stock_name: str,
        rule_scores: Dict[str, Any],
        metrics: Dict[str, Any],
        news_items: List[Dict],
    ) -> Dict[str, Any]:
        total_score = int(rule_scores.get("total", 0) or 0)
        if self.provider == "codex" and self._codex_sender:
            return await self._analyze_overall_with_codex(stock_name, rule_scores, metrics, news_items)
        if self.provider == "gemini" and self._gemini_model:
            return await self._analyze_overall_with_gemini(stock_name, rule_scores, metrics, news_items)
        return self._default_overall(
            stock_name=stock_name,
            total_score=total_score,
            reason="AI 모델이 준비되지 않아 규칙 기반 해설을 제공합니다.",
            rule_scores=rule_scores,
            metrics=metrics,
            news_items=news_items,
        )

    async def _collect_codex_output(self, prompt: str) -> str:
        conversation_history = [{"role": "user", "content": prompt}]
        instructions = "You are a Korean stock news analyst. Return strict JSON only."
        if self._codex_sender is not None:
            accumulator = ""
            async for line in self._codex_sender(
                conversation_history=conversation_history,
                model=self._codex_model,
                instructions=instructions,
                reasoning_effort=self.reasoning_effort,
            ):
                if not str(line).startswith("data: "):
                    continue
                payload = str(line)[6:].strip()
                if payload == "[DONE]":
                    continue

                try:
                    parsed = json.loads(payload)
                except Exception:
                    continue

                event_type = parsed.get("type")
                if event_type == "response.output_text.delta":
                    delta = str(parsed.get("delta", "") or "")
                    if delta:
                        accumulator += delta
                elif event_type == "response.output_text.done":
                    text = str(parsed.get("text", "") or "")
                    if text:
                        accumulator = text
                elif event_type == "response.completed":
                    continue

            return accumulator.strip()

        if self._codex_transport == "responses_api" and self._openai_api_key:
            return await asyncio.to_thread(
                self._collect_codex_output_via_responses,
                prompt,
                instructions,
            )

        raise LLMProviderError(self.get_not_ready_reason())

    async def generate_json(
        self,
        prompt: str,
        *,
        instructions: str = "Return strict JSON only.",
        fallback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        default_value = dict(fallback or {})
        try:
            if self.provider == "codex" and (self._codex_sender or (self._codex_transport == "responses_api" and self._openai_api_key)):
                conversation_history = [{"role": "user", "content": prompt}]
                if self._codex_sender is not None:
                    accumulator = ""
                    async for line in self._codex_sender(
                        conversation_history=conversation_history,
                        model=self._codex_model,
                        instructions=instructions,
                        reasoning_effort=self.reasoning_effort,
                    ):
                        if not str(line).startswith("data: "):
                            continue
                        payload = str(line)[6:].strip()
                        if payload == "[DONE]":
                            continue
                        try:
                            parsed = json.loads(payload)
                        except Exception:
                            continue
                        event_type = parsed.get("type")
                        if event_type == "response.output_text.delta":
                            delta = str(parsed.get("delta", "") or "")
                            if delta:
                                accumulator += delta
                        elif event_type == "response.output_text.done":
                            text = str(parsed.get("text", "") or "")
                            if text:
                                accumulator = text
                    data = _extract_json_object(accumulator.strip())
                    return data or default_value

                text = await asyncio.to_thread(self._collect_codex_output_via_responses, prompt, instructions)
                data = _extract_json_object(text)
                return data or default_value
        except Exception:
            return default_value
        return default_value

    def _collect_codex_output_via_responses(self, prompt: str, instructions: str) -> str:
        headers = {
            "Authorization": f"Bearer {self._openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._codex_model,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            "reasoning": {"effort": self.reasoning_effort},
        }
        resp = requests.post(
            f"{self._openai_base_url}/responses",
            headers=headers,
            json=payload,
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        obj = resp.json()
        output_text = str(obj.get("output_text", "") or "").strip()
        if output_text:
            return output_text

        outputs = obj.get("output")
        if isinstance(outputs, list):
            parts: List[str] = []
            for item in outputs:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    if str(c.get("type", "")) in {"output_text", "text"}:
                        t = str(c.get("text", "") or "").strip()
                        if t:
                            parts.append(t)
            if parts:
                return "\n".join(parts)

        raise LLMProviderError("responses api returned no text output")

    def _apply_trade_policy_to_overall(
        self,
        *,
        stock_name: str,
        total_score: int,
        metrics: Dict[str, Any],
        opinion: str,
        summary: str,
        meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        market_context = metrics.get("market_context") if isinstance(metrics.get("market_context"), dict) else {}
        program_context = metrics.get("program_context") if isinstance(metrics.get("program_context"), dict) else {}
        external_market_context = (
            metrics.get("external_market_context")
            if isinstance(metrics.get("external_market_context"), dict)
            else {}
        )
        market_policy = metrics.get("market_policy") if isinstance(metrics.get("market_policy"), dict) else None
        decision = decide_trade_opinion(
            grade=metrics.get("base_grade", metrics.get("grade")),
            total_score=total_score,
            market_context=market_context,
            program_context=program_context,
            external_market_context=external_market_context,
            grade_policy=market_policy,
            fresh_news_count=metrics.get("fresh_news_count"),
        )
        final_opinion = str(decision.get("opinion", "매도") or "매도")
        final_summary = str(summary or "").strip()
        if opinion != final_opinion:
            prefix = " ".join(str(x).strip() for x in decision.get("reasons", []) if str(x).strip())
            final_summary = f"{prefix} {final_summary}".strip()
        if not final_summary:
            final_summary = f"규칙 점수 {total_score}/{TOTAL_RULE_SCORE_MAX} 기준으로 {final_opinion} 의견입니다."

        out_meta = dict(meta or {})
        out_meta["stock"] = stock_name
        out_meta["total_score"] = total_score
        out_meta["decision"] = decision
        out_meta["market_context"] = market_context
        out_meta["program_context"] = program_context
        out_meta["external_market_context"] = external_market_context
        if market_policy:
            out_meta["market_policy"] = dict(market_policy)
        return {
            "opinion": final_opinion,
            "summary": final_summary,
            "meta": out_meta,
        }

    async def _analyze_with_codex(self, stock_name: str, news_items: List[Dict]) -> Dict[str, Any]:
        rows: List[str] = []
        for idx, item in enumerate(news_items, 1):
            title = str(item.get("title", "") or "").strip()
            summary = str(item.get("summary", "") or "").strip()
            source = str(item.get("source", "") or "").strip()
            published_at = str(item.get("published_at", "") or "").strip()
            rows.append(
                f"[{idx}] title={title}\nsummary={summary[:350]}\nsource={source}\npublished_at={published_at}\n"
            )

        prompt = (
            f"종목명: {stock_name}\n"
            "아래 뉴스만 보고 0~3 점수로 재료 강도를 평가해.\n"
            "반드시 JSON 하나만 출력해.\n"
            "스키마: {\"score\":0-3,\"reason\":\"핵심 근거\",\"risks\":[\"리스크\"],\"confidence\":\"low|medium|high\",\"material_strength\":0-3,\"attention_score\":0-2,\"novelty_score\":0-2,\"entity_confidence\":0-1,\"category\":\"earnings|contract|policy|theme|clinical|supply|rumor|other\",\"tone\":\"positive|mixed|negative\"}\n"
            "규칙: 뉴스가 약하거나 혼재면 1, 뚜렷한 악재면 0, 강한 모멘텀이면 2~3. 화제성(attention)은 시장이 실제 주목하는 정도다.\n\n"
            "뉴스:\n"
            + "\n".join(rows)
        )

        try:
            text = await asyncio.wait_for(self._collect_codex_output(prompt), timeout=self.timeout_sec)
            data = _extract_json_object(text)
            if not data:
                return self._default_result(
                    reason="Codex 응답 JSON 파싱 실패로 기본점수 1점을 적용했습니다.",
                    status="PARSE_ERROR",
                    stock_name=stock_name,
                )

            score = _clamp_score(data.get("score"), default=self.default_news_score)
            reason = str(data.get("reason", "") or "").strip() or "Codex 분석 결과"
            confidence = str(data.get("confidence", "") or "").strip().lower() or "medium"
            risks = data.get("risks")
            if not isinstance(risks, list):
                risks = []
            material_strength = _to_float(data.get("material_strength"), score)
            attention_score = _to_float(data.get("attention_score"), 0.0)
            novelty_score = _to_float(data.get("novelty_score"), 0.0)
            entity_confidence = _to_float(data.get("entity_confidence"), 0.0)
            category = str(data.get("category", "") or "").strip()
            tone = str(data.get("tone", "") or "").strip().lower()

            meta = {
                "status": "OK",
                "provider": "codex",
                "model": self._codex_model,
                "reasoning_effort": self.reasoning_effort,
                "confidence": confidence,
                "risks": risks,
                "stock": stock_name,
                "material_strength": round(max(0.0, min(3.0, material_strength)), 2),
                "attention_score": round(max(0.0, min(2.0, attention_score)), 2),
                "novelty_score": round(max(0.0, min(2.0, novelty_score)), 2),
                "entity_confidence": round(max(0.0, min(1.0, entity_confidence)), 2),
                "category": category,
                "tone": tone,
            }
            return {
                "score": score,
                "reason": reason,
                "status": "OK",
                "provider": "codex",
                "model": self._codex_model,
                "reasoning_effort": self.reasoning_effort,
                "meta": meta,
            }
        except asyncio.TimeoutError:
            return self._default_result(
                reason="Codex 분석 시간 초과로 기본점수 1점을 적용했습니다.",
                status="TIMEOUT",
                stock_name=stock_name,
            )
        except Exception:
            return self._default_result(
                reason="Codex 분석 실패로 기본점수 1점을 적용했습니다.",
                status="ERROR",
                stock_name=stock_name,
            )

    async def _analyze_overall_with_codex(
        self,
        stock_name: str,
        rule_scores: Dict[str, Any],
        metrics: Dict[str, Any],
        news_items: List[Dict],
    ) -> Dict[str, Any]:
        total_score = int(rule_scores.get("total", 0) or 0)
        news_lines: List[str] = []
        for i, item in enumerate(news_items[:3], 1):
            news_lines.append(
                f"[{i}] title={str(item.get('title', '')).strip()}\n"
                f"summary={str(item.get('summary', '')).strip()[:320]}"
            )

        prompt = (
            f"종목명: {stock_name}\n"
            f"뉴스 유효 구간: {_fresh_news_label(metrics)}\n"
            f"규칙점수: {json.dumps(rule_scores, ensure_ascii=False)}\n"
            f"핵심지표: {json.dumps(metrics, ensure_ascii=False)}\n"
            "뉴스요약:\n"
            + ("\n".join(news_lines) if news_lines else "- 없음")
            + "\n\n"
            "너는 종가배팅 전략 분석가다.\n"
            "규칙점수와 지표를 바탕으로 최종의견을 내려라.\n"
            "정책: 시장 보정 후 C등급이면 신규 매수 금지, 시장 상태가 '시장 약세'면 신규 매수 금지, 시장 상태가 '시장 주의'이면 시장 보정 후 B등급 신규 매수 금지.\n"
            "설명에는 RISK_OFF, CAUTION, range, WATCH 같은 영어 코드명을 쓰지 말고 쉬운 한국어만 사용해라.\n"
            "summary 안에는 반드시 마지막에 '목표가 : 숫자', '손절가 : 숫자' 줄을 포함해라.\n"
            "반드시 JSON 한 개만 출력:\n"
            '{"opinion":"매수|매도","summary":"4~6문장 상세 근거","evidence":["근거1","근거2"],"risks":["리스크1"],"confidence":"low|medium|high"}'
        )

        try:
            text = await asyncio.wait_for(self._collect_codex_output(prompt), timeout=self.timeout_sec)
            data = _extract_json_object(text)
            if not data:
                return self._default_overall(
                    stock_name=stock_name,
                    total_score=total_score,
                    reason="Codex 전체평가 JSON 파싱 실패로 규칙기반 기본의견을 사용했습니다.",
                    rule_scores=rule_scores,
                    metrics=metrics,
                    news_items=news_items,
                )

            opinion_raw = str(data.get("opinion", "") or "").strip()
            opinion = "매수" if opinion_raw in {"매수", "BUY", "buy"} else "매도"
            summary = str(data.get("summary", "") or "").strip()
            raw_evidence = data.get("evidence")
            evidence_list = list(raw_evidence) if isinstance(raw_evidence, list) else []
            evidence = [str(x).strip() for x in evidence_list if str(x).strip()][:3]
            raw_risks = data.get("risks")
            risks_list = list(raw_risks) if isinstance(raw_risks, list) else []
            risks = [str(x).strip() for x in risks_list if str(x).strip()][:3]
            if len(summary) < 40:
                rb = self._build_rule_based_summary(
                    stock_name=stock_name,
                    total_score=total_score,
                    rule_scores=rule_scores,
                    metrics=metrics,
                    news_items=news_items,
                    reason="",
                )
                base = str(summary or "").strip()
                summary = (f"{base} " if base else "") + rb["summary"]
                if not evidence:
                    evidence = rb["evidence"][:3]
            if not summary:
                summary = f"규칙 점수 {total_score}/{TOTAL_RULE_SCORE_MAX} 기준으로 {opinion} 의견입니다."
            trade_levels = _format_trade_levels(metrics)
            if "목표가 :" not in summary or "손절가 :" not in summary:
                summary = f"{summary.rstrip()}\n{trade_levels}"
            confidence = str(data.get("confidence", "") or "").strip().lower() or "medium"
            policy_applied = self._apply_trade_policy_to_overall(
                stock_name=stock_name,
                total_score=total_score,
                metrics=metrics,
                opinion=opinion,
                summary=summary,
                meta={
                    "status": "OK",
                    "provider": "codex",
                    "model": self._codex_model,
                    "reasoning_effort": self.reasoning_effort,
                    "confidence": confidence,
                    "evidence": evidence,
                    "risks": risks,
                },
            )
            return {
                "opinion": policy_applied["opinion"],
                "summary": policy_applied["summary"],
                "status": "OK",
                "provider": "codex",
                "model": self._codex_model,
                "reasoning_effort": self.reasoning_effort,
                "meta": policy_applied["meta"],
            }
        except Exception:
            return self._default_overall(
                stock_name=stock_name,
                total_score=total_score,
                reason="Codex 전체평가 실패로 규칙기반 기본의견을 사용했습니다.",
                rule_scores=rule_scores,
                metrics=metrics,
                news_items=news_items,
            )

    async def _analyze_with_gemini(self, stock_name: str, news_items: List[Dict]) -> Dict[str, Any]:
        if not self._gemini_model:
            return self._default_result(
                reason="Gemini 모델이 없어 기본점수 1점을 적용했습니다.",
                status="NO_MODEL",
                stock_name=stock_name,
            )

        news_text = ""
        for i, news in enumerate(news_items, 1):
            title = str(news.get("title", "") or "").strip()
            summary = str(news.get("summary", "") or "").strip()[:300]
            news_text += f"[{i}] title: {title}\nsummary: {summary}\n\n"

        prompt = f"""
You are analyzing Korean stock news for {stock_name}.
Return one JSON object only:
{{"score": <0~3 int>, "reason": "<short reason>", "confidence": "low|medium|high", "material_strength": <0~3 float>, "attention_score": <0~2 float>, "novelty_score": <0~2 float>, "entity_confidence": <0~1 float>, "category": "earnings|contract|policy|theme|clinical|supply|rumor|other", "tone": "positive|mixed|negative"}}

News:
{news_text}
"""

        try:
            response = await asyncio.to_thread(
                self._gemini_model.generate_content,
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )
            text = (response.text or "").strip()
            data = _extract_json_object(text)
            if not data:
                raise ValueError("invalid gemini json")

            score = _clamp_score(data.get("score"), default=self.default_news_score)
            reason = str(data.get("reason", "") or "").strip() or "Gemini 분석 결과"
            confidence = str(data.get("confidence", "") or "").strip().lower() or "medium"
            material_strength = _to_float(data.get("material_strength"), score)
            attention_score = _to_float(data.get("attention_score"), 0.0)
            novelty_score = _to_float(data.get("novelty_score"), 0.0)
            entity_confidence = _to_float(data.get("entity_confidence"), 0.0)
            category = str(data.get("category", "") or "").strip()
            tone = str(data.get("tone", "") or "").strip().lower()
            return {
                "score": score,
                "reason": reason,
                "status": "OK",
                "provider": "gemini",
                "model": str(self.model or ""),
                "reasoning_effort": "n/a",
                "meta": {
                    "status": "OK",
                    "provider": "gemini",
                    "model": str(self.model or ""),
                    "reasoning_effort": "n/a",
                    "confidence": confidence,
                    "stock": stock_name,
                    "material_strength": round(max(0.0, min(3.0, material_strength)), 2),
                    "attention_score": round(max(0.0, min(2.0, attention_score)), 2),
                    "novelty_score": round(max(0.0, min(2.0, novelty_score)), 2),
                    "entity_confidence": round(max(0.0, min(1.0, entity_confidence)), 2),
                    "category": category,
                    "tone": tone,
                },
            }
        except Exception:
            return self._default_result(
                reason="Gemini 분석 실패로 기본점수 1점을 적용했습니다.",
                status="ERROR",
                stock_name=stock_name,
            )

    async def _analyze_overall_with_gemini(
        self,
        stock_name: str,
        rule_scores: Dict[str, Any],
        metrics: Dict[str, Any],
        news_items: List[Dict],
    ) -> Dict[str, Any]:
        total_score = int(rule_scores.get("total", 0) or 0)
        if not self._gemini_model:
            return self._default_overall(
                stock_name=stock_name,
                total_score=total_score,
                reason="Gemini 모델이 준비되지 않아 규칙 기반 해설을 제공합니다.",
                rule_scores=rule_scores,
                metrics=metrics,
                news_items=news_items,
            )

        prompt = f"""
종목명: {stock_name}
뉴스 유효 구간: {_fresh_news_label(metrics)}
규칙점수: {json.dumps(rule_scores, ensure_ascii=False)}
핵심지표: {json.dumps(metrics, ensure_ascii=False)}

반드시 JSON 하나만 출력:
{{"opinion":"매수|매도","summary":"4~6문장 상세 근거","evidence":["근거1","근거2"],"risks":["리스크1"],"confidence":"low|medium|high"}}
summary 마지막에는 반드시 "목표가 : 숫자", "손절가 : 숫자" 줄을 포함해라.
정책: 시장 보정 후 C등급이면 신규 매수 금지, 시장 상태가 '시장 약세'면 신규 매수 금지, 시장 상태가 '시장 주의'이면 시장 보정 후 B등급 신규 매수 금지.
설명에는 영어 코드명(RISK_OFF, CAUTION, range, WATCH)을 쓰지 말고 쉬운 한국어만 사용해라.
"""
        try:
            response = await asyncio.to_thread(
                self._gemini_model.generate_content,
                prompt,
                generation_config={"response_mime_type": "application/json"},
            )
            data = _extract_json_object(str(getattr(response, "text", "") or ""))
            if not data:
                raise ValueError("invalid gemini json")
            opinion_raw = str(data.get("opinion", "") or "").strip()
            opinion = "매수" if opinion_raw in {"매수", "BUY", "buy"} else "매도"
            summary = str(data.get("summary", "") or "").strip() or f"규칙 점수 {total_score}/{TOTAL_RULE_SCORE_MAX} 기준 {opinion} 의견입니다."
            raw_evidence = data.get("evidence")
            evidence_list = list(raw_evidence) if isinstance(raw_evidence, list) else []
            evidence = [str(x).strip() for x in evidence_list if str(x).strip()][:3]
            raw_risks = data.get("risks")
            risks_list = list(raw_risks) if isinstance(raw_risks, list) else []
            risks = [str(x).strip() for x in risks_list if str(x).strip()][:3]
            if len(summary) < 40:
                rb = self._build_rule_based_summary(
                    stock_name=stock_name,
                    total_score=total_score,
                    rule_scores=rule_scores,
                    metrics=metrics,
                    news_items=news_items,
                    reason="",
                )
                summary = f"{summary} {rb['summary']}".strip()
                if not evidence:
                    evidence = rb["evidence"][:3]
            trade_levels = _format_trade_levels(metrics)
            if "목표가 :" not in summary or "손절가 :" not in summary:
                summary = f"{summary.rstrip()}\n{trade_levels}"
            confidence = str(data.get("confidence", "") or "").strip().lower() or "medium"
            policy_applied = self._apply_trade_policy_to_overall(
                stock_name=stock_name,
                total_score=total_score,
                metrics=metrics,
                opinion=opinion,
                summary=summary,
                meta={
                    "status": "OK",
                    "provider": "gemini",
                    "model": str(self.model or ""),
                    "reasoning_effort": "n/a",
                    "confidence": confidence,
                    "evidence": evidence,
                    "risks": risks,
                },
            )
            return {
                "opinion": policy_applied["opinion"],
                "summary": policy_applied["summary"],
                "status": "OK",
                "provider": "gemini",
                "model": str(self.model or ""),
                "reasoning_effort": "n/a",
                "meta": policy_applied["meta"],
            }
        except Exception:
            return self._default_overall(
                stock_name=stock_name,
                total_score=total_score,
                reason="Gemini 전체평가 실패로 규칙기반 기본의견을 사용했습니다.",
                rule_scores=rule_scores,
                metrics=metrics,
                news_items=news_items,
            )

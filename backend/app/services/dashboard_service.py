from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from batch.runtime_source.engine.decision_policy import decide_trade_opinion
from batch.runtime_source.engine.human_labels import decision_status_label, humanize_text, market_status_label, minute_pattern_label
from batch.runtime_source.engine.llm_analyzer import LLMAnalyzer
from batch.runtime_source.engine.scoring_constants import score_quality_grade
from batch.runtime_source.engine.theme_classifier import infer_theme
from batch.runtime_source.providers.kiwoom_client import KiwoomRESTClient
from backend.app.repositories.dashboard_repository import DashboardRepository
from backend.app.schemas.dashboard import DashboardAccountPayload, DashboardAccountPosition, DashboardMarketItem, DashboardPickPayload, DashboardResponse
from backend.app.services.pick_selector import select_official_candidates
from backend.app.services.view_helpers import resolve_signal_grades, safe_dt, safe_float, safe_int


MAX_DASHBOARD_PICKS = 5


class DashboardService:
    def __init__(self, repository: DashboardRepository | None = None) -> None:
        self.repository = repository or DashboardRepository()
        self._use_llm_reports = str(os.getenv('DASHBOARD_LLM_REPORTS', '0')).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
        try:
            self._analyzer = LLMAnalyzer()
        except Exception:
            self._analyzer = None

    def _cache_is_fresh(self, cached: dict[str, Any]) -> bool:
        updated_at = safe_dt(cached.get('cached_updated_at'))
        if updated_at is None:
            return False
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        age_sec = (datetime.now(timezone.utc) - updated_at.astimezone(timezone.utc)).total_seconds()
        return age_sec <= 300

    def _build_market_summary(self, market_rows: list[dict[str, Any]], program_rows: list[dict[str, Any]]) -> tuple[list[DashboardMarketItem], str]:
        program_map = {
            str(row.get("market", "")).upper(): row
            for row in program_rows
        }
        items: list[DashboardMarketItem] = []
        summary_parts: list[str] = []
        for row in market_rows:
            market = str(row.get("market", "")).upper()
            program = program_map.get(market, {})
            item = DashboardMarketItem(
                market=market,
                market_label=str(row.get("market_label", market)),
                market_status=str(row.get("market_status", "")),
                market_status_label=market_status_label(row.get("market_status", "")),
                index_value=safe_float(row.get("index_value")),
                change_pct=safe_float(row.get("change_pct")),
                rise_count=safe_int(row.get("rise_count")),
                steady_count=safe_int(row.get("steady_count")),
                fall_count=safe_int(row.get("fall_count")),
                upper_count=safe_int(row.get("upper_count")),
                lower_count=safe_int(row.get("lower_count")),
                total_net=safe_int(program.get("total_net")),
                non_arbitrage_net=safe_int(program.get("non_arbitrage_net")),
                snapshot_time=(
                    row.get("snapshot_time").isoformat()
                    if hasattr(row.get("snapshot_time"), "isoformat")
                    else None
                ),
            )
            items.append(item)
            breadth = item.rise_count - item.fall_count
            summary_parts.append(
                f"{item.market_label} {item.change_pct:+.2f}% / 상승-{item.rise_count} 하락-{item.fall_count} / 프로그램 {item.total_net:+,}"
            )
            if breadth > 0 and item.total_net > 0:
                summary_parts.append(f"{item.market_label}는 수급과 종목 breadth가 함께 우호적입니다.")
        summary = " ".join(summary_parts).strip() or "오늘 시장 요약 데이터가 아직 충분하지 않습니다."
        return items, summary

    def _attempt_refresh_account(self) -> str:
        try:
            client = KiwoomRESTClient()
            client.request('/api/dostk/stkinfo', 'kt00018', {'qry_tp': '1', 'dmst_stex_tp': 'KRX'})
            return "계좌 새로고침 시도 완료"
        except Exception as exc:
            return f"계좌 API는 수동 새로고침 때만 시도하며, 현재 권한으로는 조회되지 않습니다: {exc}"

    def _attempt_refresh_account(self) -> str:
        try:
            client = KiwoomRESTClient()
            account_info = client.request('/api/dostk/acnt', 'ka00001', {}).body
            account_no = str(account_info.get('acctNo', '') or '').strip()
            if not account_no:
                return '계좌번호 조회에 실패했습니다.'

            snapshot_body = client.request('/api/dostk/acnt', 'kt00018', {'qry_tp': '1', 'dmst_stex_tp': 'KRX'}).body
            positions_raw = snapshot_body.get('acnt_evlt_remn_indv_tot') if isinstance(snapshot_body.get('acnt_evlt_remn_indv_tot'), list) else []
            positions: list[dict[str, Any]] = []
            for item in positions_raw:
                if not isinstance(item, dict):
                    continue
                ticker = ''.join(ch for ch in str(item.get('stk_cd', '') or '') if ch.isdigit()).zfill(6)
                if not ticker:
                    continue
                positions.append(
                    {
                        'ticker': ticker,
                        'stock_name': str(item.get('stk_nm', '') or ''),
                        'quantity': abs(safe_int(item.get('rmnd_qty'))),
                        'available_qty': abs(safe_int(item.get('trde_able_qty'))),
                        'avg_price': abs(safe_float(item.get('pur_pric'))),
                        'current_price': abs(safe_float(item.get('cur_prc'))),
                        'eval_amount': abs(safe_int(item.get('evlt_amt'))),
                        'profit_amount': safe_int(item.get('evltv_prft')),
                        'profit_rate': safe_float(item.get('prft_rt')),
                    }
                )

            self.repository.save_account_snapshot(
                {
                    'account_no': account_no,
                    'snapshot_time': datetime.now(timezone.utc).isoformat(),
                    'venue': 'KRX',
                    'total_purchase_amt': abs(safe_int(snapshot_body.get('tot_pur_amt'))),
                    'total_eval_amt': abs(safe_int(snapshot_body.get('tot_evlt_amt'))),
                    'total_eval_profit': safe_int(snapshot_body.get('tot_evlt_pl')),
                    'total_profit_rate': safe_float(snapshot_body.get('tot_prft_rt')),
                    'estimated_assets': abs(safe_int(snapshot_body.get('prsm_dpst_aset_amt'))),
                    'holdings_count': len(positions),
                    'realized_profit': 0,
                    'unfilled_count': 0,
                    'total_unfilled_qty': 0,
                    'avg_fill_latency_ms': 0.0,
                    'est_slippage_bps': 0.0,
                    'raw_payload': snapshot_body,
                }
            )
            self.repository.replace_account_positions(account_no, positions)
            return f'계좌 API 동기화 완료: 계좌 {account_no}, 보유 {len(positions)}건'
        except Exception as exc:
            return f'계좌 API 동기화 실패: {exc}'

    def _sector_key(self, row: dict[str, Any]) -> str:
        sector = str(row.get("sector", "") or "").strip()
        if sector:
            return sector
        sector_meta = row.get("sector_leadership") if isinstance(row.get("sector_leadership"), dict) else {}
        if str(sector_meta.get("sector_key", "") or "").strip():
            return str(sector_meta.get("sector_key"))
        news_items = row.get("news_items") if isinstance(row.get("news_items"), list) else []
        texts = [str(item.get("title", "")) for item in news_items[:3]]
        return infer_theme(str(row.get("stock_name", "")), texts=texts, fallback="General")

    def _apply_trade_policy(self, row: dict[str, Any]) -> dict[str, Any]:
        resolved_grade, _base_grade = resolve_signal_grades(row)
        references = row.get("news_items") if isinstance(row.get("news_items"), list) else []
        market_context = row.get("market_context") if isinstance(row.get("market_context"), dict) else {}
        program_context = row.get("program_context") if isinstance(row.get("program_context"), dict) else {}
        external_market_context = row.get("external_market_context") if isinstance(row.get("external_market_context"), dict) else {}
        market_policy = row.get("market_policy") if isinstance(row.get("market_policy"), dict) else {}
        policy = decide_trade_opinion(
            grade=resolved_grade,
            total_score=safe_int(row.get("score_total")),
            market_context=market_context,
            program_context=program_context,
            external_market_context=external_market_context,
            grade_policy=market_policy,
            fresh_news_count=len(references),
            material_news_count=row.get("material_news_count"),
            negative_news_count=row.get("negative_news_count"),
            news_tone=row.get("news_tone"),
        )
        updated = dict(row)
        updated["decision_status"] = str(policy.get("status") or row.get("decision_status") or "WATCH").upper()
        updated["ai_opinion"] = str(policy.get("opinion") or row.get("ai_opinion") or "")
        return updated

    def _fallback_pick_report(self, row: dict[str, Any]) -> dict[str, Any]:
        intraday = {
            "venue": str(row.get("venue", "") or ""),
            "orderbook_imbalance": safe_float(row.get("orderbook_imbalance")),
            "execution_strength": safe_float(row.get("execution_strength")),
            "minute_pattern": str(row.get("minute_pattern", "") or ""),
            "minute_breakout_score": safe_float(row.get("minute_breakout_score")),
            "volume_surge_ratio": safe_float(row.get("volume_surge_ratio")),
            "orderbook_surge_ratio": safe_float(row.get("orderbook_surge_ratio")),
            "vi_active": bool(row.get("vi_active", False)),
            "vi_type": str(row.get("vi_type", "") or ""),
            "condition_hit_count": safe_int(row.get("condition_hit_count")),
            "condition_names": row.get("condition_names") if isinstance(row.get("condition_names"), list) else [],
            "acc_trade_value": safe_int(row.get("acc_trade_value")),
            "acc_trade_volume": safe_int(row.get("acc_trade_volume")),
        }
        key_points = [
            f"등급 {row.get('grade')} (raw {row.get('base_grade', row.get('grade'))}) / 총점 {safe_int(row.get('score_total'))}",
            f"외인 5일 {safe_int(row.get('foreign_5d')):+,}, 기관 5일 {safe_int(row.get('inst_5d')):+,}",
            f"호가 불균형 {intraday['orderbook_imbalance']:+.2f}, 체결강도 {intraday['execution_strength']:.1f}",
            f"분봉 패턴 {minute_pattern_label(intraday['minute_pattern'])} / 거래량 배수 {intraday['volume_surge_ratio']:.2f}",
        ]
        return {
            "title": f"{row.get('stock_name')} 리포트",
            "body": (
                f"{row.get('stock_name')}은(는) {row.get('grade')} 등급 후보 중 하나이며, "
                f"원등급은 {row.get('base_grade', row.get('grade'))}이고 현재 판정 상태는 {decision_status_label(row.get('decision_status', 'WATCH'))}입니다. "
                f"현재가 {safe_float(row.get('current_price')):,.0f}원, 등락률 {safe_float(row.get('change_pct')):+.2f}%입니다. "
                f"실시간 체결강도와 호가 불균형을 함께 볼 때 단기 매수 우위가 {'유지' if intraday['execution_strength'] >= 100 else '약화'}되고 있습니다. "
                f"분봉 패턴은 {minute_pattern_label(intraday['minute_pattern'])}로 보이며, 목표가 {safe_float(row.get('target_price')):,.0f}원 / 손절가 {safe_float(row.get('stop_price')):,.0f}원 기준으로 대응합니다."
            ),
            "key_points": key_points,
        }

    async def _generate_pick_report(self, market_summary: str, row: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback_pick_report(row)
        prompt = (
            f"시장 요약: {market_summary}\n"
            f"종목명: {row.get('stock_name')} ({row.get('stock_code')})\n"
            f"시장/섹터: {row.get('market')} / {row.get('sector')}\n"
            f"등급/점수: {row.get('grade')} (raw {row.get('base_grade', row.get('grade'))}) / {safe_int(row.get('score_total'))}\n"
            f"판정상태: {decision_status_label(row.get('decision_status'))} / AI의견: {row.get('ai_opinion')}\n"
            f"가격: 현재 {safe_float(row.get('current_price'))}, 진입 {safe_float(row.get('entry_price'))}, 목표 {safe_float(row.get('target_price'))}, 손절 {safe_float(row.get('stop_price'))}\n"
            f"수급: 외인5일 {safe_int(row.get('foreign_5d'))}, 기관5일 {safe_int(row.get('inst_5d'))}\n"
            f"실시간성: venue={row.get('venue')}, orderbook_imbalance={safe_float(row.get('orderbook_imbalance'))}, execution_strength={safe_float(row.get('execution_strength'))}, "
            f"분봉패턴={minute_pattern_label(row.get('minute_pattern'))}, breakout_score={safe_float(row.get('minute_breakout_score'))}, volume_surge_ratio={safe_float(row.get('volume_surge_ratio'))}\n"
            f"기존 AI 요약: {row.get('ai_summary')}\n"
            "위 정보를 바탕으로 장중/장후 대응 관점의 심층 종목 리포트를 작성해.\n"
            "영어 코드명(RISK_OFF, CAUTION, range, WATCH 같은 내부 코드)은 절대 쓰지 말고 누구나 이해하는 쉬운 한국어 표현만 사용해.\n"
            "반드시 JSON 하나만 출력:\n"
            '{"title":"짧은 제목","body":"6~9문장 보고서","key_points":["포인트1","포인트2","포인트3"]}'
        )
        if self._analyzer is None:
            return fallback
        result = await self._analyzer.generate_json(
            prompt,
            instructions="You are a Korean equity strategist. Return strict JSON only.",
            fallback=fallback,
        )
        return result or fallback

    async def _generate_pick_report_with_timeout(self, market_summary: str, row: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback_pick_report(row)
        if not self._use_llm_reports or self._analyzer is None:
            return fallback
        try:
            return await asyncio.wait_for(self._generate_pick_report(market_summary, row), timeout=4)
        except Exception:
            return fallback

    async def _build_dashboard(self, refresh_account: bool) -> DashboardResponse:
        market_rows = self.repository.fetch_market_rows()
        program_rows = self.repository.fetch_program_rows()
        candidate_rows = self.repository.fetch_latest_candidates(limit=200)
        account_row = self.repository.fetch_account_snapshot()
        account_positions_rows = self.repository.fetch_account_positions(account_row.get("account_no") if account_row else None)
        account_note = "계좌는 Dashboard Refresh 시에만 조회를 시도합니다."
        if refresh_account:
            account_note = self._attempt_refresh_account()
            account_row = self.repository.fetch_account_snapshot()
            account_positions_rows = self.repository.fetch_account_positions(account_row.get("account_no") if account_row else None)

        markets, market_summary = self._build_market_summary(market_rows, program_rows)
        tracked_codes = self.repository.fetch_latest_tracked_pick_codes()
        rows_by_code = {str(row.get("stock_code", "") or "").zfill(6): row for row in candidate_rows}
        picks_rows = [rows_by_code[code] for code in tracked_codes if code in rows_by_code][:MAX_DASHBOARD_PICKS]
        if not picks_rows:
            picks_rows = select_official_candidates(candidate_rows, max_items=MAX_DASHBOARD_PICKS)
        picks_rows = [self._apply_trade_policy(row) for row in picks_rows]
        reports = await asyncio.gather(*[self._generate_pick_report_with_timeout(market_summary, row) for row in picks_rows]) if picks_rows else []

        picks: list[DashboardPickPayload] = []
        for row, report in zip(picks_rows, reports):
            resolved_grade, base_grade = resolve_signal_grades(row)
            references = row.get("news_items") if isinstance(row.get("news_items"), list) else []
            ai_evidence = row.get("ai_evidence") if isinstance(row.get("ai_evidence"), list) else []
            score_total = safe_int(row.get("score_total"))
            quality_grade = score_quality_grade(score_total)
            picks.append(
                DashboardPickPayload(
                    ticker=str(row.get("stock_code", "")).zfill(6),
                    name=str(row.get("stock_name", "")),
                    market=str(row.get("market", "")),
                    sector=self._sector_key(row),
                    grade=resolved_grade,
                    base_grade=base_grade,
                    quality_grade=quality_grade,
                    quality_label=f"퀄리티 {quality_grade}",
                    decision_status=str(row.get("decision_status", "WATCH") or "WATCH"),
                    decision_label=decision_status_label(row.get("decision_status", "WATCH")),
                    score_total=score_total,
                    trading_value=safe_int(row.get("trading_value")),
                    change_pct=safe_float(row.get("change_pct")),
                    current_price=safe_float(row.get("current_price")),
                    entry_price=safe_float(row.get("entry_price")),
                    target_price=safe_float(row.get("target_price")),
                    stop_price=safe_float(row.get("stop_price")),
                    foreign_1d=safe_int(row.get("foreign_1d")),
                    inst_1d=safe_int(row.get("inst_1d")),
                    foreign_5d=safe_int(row.get("foreign_5d")),
                    inst_5d=safe_int(row.get("inst_5d")),
                    venue=str(row.get("venue", "") or ""),
                    ai_summary=humanize_text(str(row.get("ai_summary", "") or "")),
                    ai_evidence=[humanize_text(str(item)) for item in ai_evidence if str(item).strip()][:4],
                    report_title=humanize_text(str(report.get("title", "") or "")),
                    report_body=humanize_text(str(report.get("body", "") or "")),
                    key_points=[humanize_text(str(item)) for item in report.get("key_points", []) if str(item).strip()][:5],
                    references=references[:4],
                    intraday={
                        "orderbook_imbalance": safe_float(row.get("orderbook_imbalance")),
                        "execution_strength": safe_float(row.get("execution_strength")),
                        "minute_pattern": str(row.get("minute_pattern", "") or ""),
                        "minute_breakout_score": safe_float(row.get("minute_breakout_score")),
                        "volume_surge_ratio": safe_float(row.get("volume_surge_ratio")),
                        "orderbook_surge_ratio": safe_float(row.get("orderbook_surge_ratio")),
                        "vi_active": bool(row.get("vi_active", False)),
                        "vi_type": str(row.get("vi_type", "") or ""),
                        "condition_hit_count": safe_int(row.get("condition_hit_count")),
                        "condition_names": row.get("condition_names") if isinstance(row.get("condition_names"), list) else [],
                        "acc_trade_value": safe_int(row.get("acc_trade_value")),
                        "acc_trade_volume": safe_int(row.get("acc_trade_volume")),
                    },
                    minute_pattern_label=minute_pattern_label(row.get("minute_pattern", "")),
                )
            )

        account_positions = [
            DashboardAccountPosition(
                ticker=str(row.get("ticker", "")).zfill(6),
                stock_name=str(row.get("stock_name", "") or ""),
                quantity=safe_int(row.get("quantity")),
                available_qty=safe_int(row.get("available_qty")),
                avg_price=safe_float(row.get("avg_price")),
                current_price=safe_float(row.get("current_price")),
                eval_amount=safe_int(row.get("eval_amount")),
                profit_amount=safe_int(row.get("profit_amount")),
                profit_rate=safe_float(row.get("profit_rate")),
            )
            for row in account_positions_rows
        ]

        account = DashboardAccountPayload(note=account_note, positions=account_positions)
        if account_row:
            account = DashboardAccountPayload(
                available=True,
                account_no=str(account_row.get("account_no", "")),
                snapshot_time=account_row.get("snapshot_time").isoformat() if hasattr(account_row.get("snapshot_time"), "isoformat") else None,
                venue=str(account_row.get("venue", "") or ""),
                total_purchase_amt=safe_int(account_row.get("total_purchase_amt")),
                total_eval_amt=safe_int(account_row.get("total_eval_amt")),
                total_eval_profit=safe_int(account_row.get("total_eval_profit")),
                total_profit_rate=safe_float(account_row.get("total_profit_rate")),
                estimated_assets=safe_int(account_row.get("estimated_assets")),
                holdings_count=safe_int(account_row.get("holdings_count")),
                realized_profit=safe_int(account_row.get("realized_profit")),
                unfilled_count=safe_int(account_row.get("unfilled_count")),
                total_unfilled_qty=safe_int(account_row.get("total_unfilled_qty")),
                avg_fill_latency_ms=safe_float(account_row.get("avg_fill_latency_ms")),
                est_slippage_bps=safe_float(account_row.get("est_slippage_bps")),
                note=account_note,
                positions=account_positions,
            )

        date_text = market_rows[0].get("trade_date").isoformat() if market_rows and hasattr(market_rows[0].get("trade_date"), "isoformat") else ""
        return DashboardResponse(
            date=date_text,
            market_summary=market_summary,
            markets=markets,
            picks=picks,
            account=account,
        )

    async def get_dashboard(self, refresh_account: bool = False, force_refresh: bool = False) -> DashboardResponse:
        if not refresh_account and not force_refresh:
            cached = self.repository.fetch_cached_dashboard()
            if isinstance(cached, dict) and cached and self._cache_is_fresh(cached):
                try:
                    return DashboardResponse.model_validate(cached)
                except Exception:
                    pass

        dashboard = await self._build_dashboard(refresh_account=refresh_account)
        self.repository.save_cached_dashboard(dashboard.model_dump(mode='json'))
        return dashboard

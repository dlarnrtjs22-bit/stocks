from __future__ import annotations

# 이 파일은 종가배팅 화면 응답을 조립한다.
from datetime import datetime, timezone
from typing import Any

from batch.runtime_source.engine.decision_policy import decide_trade_opinion
from batch.runtime_source.engine.human_labels import analysis_status_label, decision_status_label, humanize_text, market_status_label, minute_pattern_label
from batch.runtime_source.engine.scoring_constants import TOTAL_RULE_SCORE_MAX
from backend.app.repositories.read_repository import ReadRepository
from backend.app.schemas.closing_bet import BasisPayload, BasisSourceItem, ClosingBetItem, ClosingBetResponse, PaginationPayload
from backend.app.services.nxt_lookup import get_nxt_lookup, recommended_plan
from backend.app.services.view_helpers import infer_signal_grade, infer_themes, normalize_date_arg, safe_float, safe_int, safe_dt, time_ago


FEATURED_PICK_LIMIT = 5


# 이 서비스는 종가배팅 화면 전체 응답을 만든다.
class ClosingBetService:
    def __init__(self, repository: ReadRepository | None = None) -> None:
        self.repository = repository or ReadRepository()

    # 이 메서드는 날짜 드롭다운용 run 날짜 목록을 반환한다.
    def list_dates(self) -> dict[str, Any]:
        dates = self.repository.list_run_dates()
        return {'dates': dates, 'latest': dates[0] if dates else None}

    # 이 메서드는 runtime_meta 에서 기준 정보 패널을 조립한다.
    def _build_basis(self, request_date: str, run_meta: dict[str, Any] | None) -> BasisPayload:
        runtime_meta = run_meta.get('runtime_meta') if isinstance(run_meta, dict) and isinstance(run_meta.get('runtime_meta'), dict) else {}
        freshness = runtime_meta.get('freshness') if isinstance(runtime_meta.get('freshness'), dict) else {}
        files = freshness.get('files') if isinstance(freshness.get('files'), dict) else {}
        run_updated_at = run_meta.get('created_at').isoformat() if isinstance(run_meta, dict) and run_meta.get('created_at') else None
        reference_data_time = str(freshness.get('reference_data_time') or '') or None

        source_map = [
            ('ohlcv_1d.csv', 'Daily Prices'),
            ('flows_1d.csv', 'Institutional Trend'),
            ('news_items.csv', 'AI Analysis'),
            ('market_context.csv', 'Market Pulse'),
            ('program_trend.csv', 'Program Trend'),
        ]
        sources: list[BasisSourceItem] = []
        latest_input_dt = None
        for file_key, label in source_map:
            file_meta = files.get(file_key) if isinstance(files.get(file_key), dict) else {}
            updated_at = str(file_meta.get('updated_at') or '') or None
            max_data_time = str(file_meta.get('max_data_time') or '') or None
            updated_dt = safe_dt(updated_at)
            if updated_dt is not None and (latest_input_dt is None or updated_dt > latest_input_dt):
                latest_input_dt = updated_dt
            sources.append(
                BasisSourceItem(
                    label=label,
                    status=str(file_meta.get('status', '') or ''),
                    updated_at=updated_at,
                    updated_ago=time_ago(updated_at),
                    max_data_time=max_data_time,
                    records=safe_int(file_meta.get('records'), 0),
                )
            )

        stale_against_inputs = False
        stale_reason = ''
        run_updated_dt = safe_dt(run_updated_at)
        if run_updated_dt is not None and latest_input_dt is not None and run_updated_dt < latest_input_dt:
            stale_against_inputs = True
            stale_reason = '입력 데이터가 현재 표시 중인 AI Jongga V2 run 보다 더 최신입니다.'

        selected_date = run_meta.get('run_date').isoformat() if isinstance(run_meta, dict) and run_meta.get('run_date') else datetime.now(timezone.utc).date().isoformat()
        return BasisPayload(
            request_date=request_date,
            selected_date=selected_date,
            run_updated_at=run_updated_at,
            run_updated_ago=time_ago(run_updated_at),
            reference_data_time=reference_data_time,
            reference_data_ago=time_ago(reference_data_time),
            stale_against_inputs=stale_against_inputs,
            stale_reason=stale_reason,
            llm_provider=str(runtime_meta.get('llm_provider', '') or ''),
            llm_model=str(runtime_meta.get('llm_model', '') or ''),
            llm_calls_used=safe_int(runtime_meta.get('llm_calls_used'), 0),
            overall_ai_top_k=safe_int(runtime_meta.get('overall_ai_top_k'), 0),
            sources=sources,
        )

    # 이 메서드는 NXT 거래 가능 여부를 lookup 해서 권장 시점/주문유형을 반환한다.
    # Design Ref: Design §6.2 — NXT 가능 → 19:40-19:55 / 불가 → 15:22-15:28
    def _nxt_plan(self, stock_code: str) -> tuple[bool, str | None, str | None]:
        entry = get_nxt_lookup().get(stock_code)
        eligible = bool(entry and entry.eligible)
        window, order_type = recommended_plan(eligible)
        return eligible, window, order_type

    # 이 메서드는 view 행 하나를 화면용 카드 데이터로 바꾼다.
    def _to_item(self, row: dict[str, Any], fallback_external_context: dict[str, Any] | None = None) -> ClosingBetItem:
        resolved_grade = infer_signal_grade(row.get('score_total'), row.get('trading_value'), row.get('change_pct'))
        references = row.get('news_items') if isinstance(row.get('news_items'), list) else []
        market_context = row.get('market_context') if isinstance(row.get('market_context'), dict) else {}
        program_context = row.get('program_context') if isinstance(row.get('program_context'), dict) else {}
        stock_program_context = row.get('stock_program_context') if isinstance(row.get('stock_program_context'), dict) else {}
        external_market_context = row.get('external_market_context') if isinstance(row.get('external_market_context'), dict) else dict(fallback_external_context or {})
        market_policy = row.get('market_policy') if isinstance(row.get('market_policy'), dict) else {}
        ai_evidence = row.get('ai_evidence') if isinstance(row.get('ai_evidence'), list) else []
        ai_breakdown = row.get('ai_breakdown') if isinstance(row.get('ai_breakdown'), dict) else {}
        score_total = safe_int(row.get('score_total'))
        ai_text = str(row.get('ai_summary') or '').strip() or 'AI 분석 결과가 없어 규칙점수 기반 기본의견을 표시합니다.'
        policy = decide_trade_opinion(
            grade=resolved_grade,
            total_score=score_total,
            market_context=market_context,
            program_context=program_context,
            external_market_context=external_market_context,
            grade_policy=market_policy,
            fresh_news_count=len(references),
        )
        opinion = str(policy.get('opinion', '매도') or '매도')
        raw_decision_status = str(row.get('decision_status') or policy.get('status') or 'WATCH').upper()
        raw_opinion = str(row.get('ai_opinion') or '').strip()
        if raw_opinion in {'매수', '매도'} and raw_opinion != opinion:
            ai_text = f"{' '.join(policy.get('reasons', []))} {ai_text}".strip()
        ai_text = humanize_text(ai_text)
        market_context = dict(market_context)
        if market_context:
            market_context['market_status_label'] = market_status_label(market_context.get('market_status'))
        external_market_context = dict(external_market_context)
        if external_market_context:
            external_market_context['status_label'] = market_status_label(external_market_context.get('status'))
        minute_pattern = ''
        intraday_pressure = row.get('intraday_pressure') if isinstance(row.get('intraday_pressure'), dict) else {}
        if isinstance(intraday_pressure, dict):
            minute_pattern = str(intraday_pressure.get('minute_pattern', '') or '')

        return ClosingBetItem(
            rank=safe_int(row.get('signal_rank'), 0),
            global_rank=safe_int(row.get('signal_rank'), 0),
            ticker=str(row.get('stock_code', '')).zfill(6),
            name=str(row.get('stock_name', '')),
            market=str(row.get('market', '')),
            grade=resolved_grade,
            base_grade=resolved_grade,
            score_total=score_total,
            score_max=TOTAL_RULE_SCORE_MAX,
            scores={
                'news': safe_int(row.get('score_news'), 0),
                'supply': safe_int(row.get('score_supply'), 0),
                'chart': safe_int(row.get('score_chart'), 0),
                'volume': safe_int(row.get('score_volume'), 0),
                'candle': safe_int(row.get('score_candle'), 0),
                'consolidation': safe_int(row.get('score_consolidation'), 0),
                'market': safe_int(row.get('score_market'), 0),
                'program': safe_int(row.get('score_program'), 0),
                'stock_program': safe_int(row.get('score_stock_program'), 0),
                'sector': safe_int(row.get('score_sector'), 0),
                'leader': safe_int(row.get('score_leader'), 0),
                'intraday': safe_int(row.get('score_intraday'), 0),
                'news_attention': safe_int(row.get('score_news_attention'), 0),
            },
            change_pct=round(safe_float(row.get('change_pct'), 0.0), 2),
            trading_value=safe_int(row.get('trading_value'), 0),
            entry_price=round(safe_float(row.get('entry_price'), 0.0), 2),
            current_price=round(safe_float(row.get('current_price'), 0.0), 2),
            target_price=round(safe_float(row.get('target_price'), 0.0), 2),
            stop_price=round(safe_float(row.get('stop_price'), 0.0), 2),
            ai_analysis=ai_text,
            analysis_status=str(row.get('ai_status') or 'NO_RESULT').upper(),
            analysis_status_label=analysis_status_label(row.get('ai_status') or 'NO_RESULT'),
            ai_opinion=opinion,
            decision_status=raw_decision_status,
            decision_label=decision_status_label(raw_decision_status),
            ai_evidence=[humanize_text(str(item).strip()) for item in ai_evidence if str(item).strip()][:3],
            ai_breakdown=ai_breakdown,
            references=references[:3],
            themes=infer_themes(str(row.get('stock_name', ''))),
            foreign_1d=safe_int(row.get('foreign_1d'), 0),
            inst_1d=safe_int(row.get('inst_1d'), 0),
            foreign_5d=safe_int(row.get('foreign_5d'), 0),
            inst_5d=safe_int(row.get('inst_5d'), 0),
            market_context=market_context,
            program_context=program_context,
            stock_program_context=stock_program_context,
            external_market_context=external_market_context,
            market_policy=market_policy,
            minute_pattern_label=minute_pattern_label(minute_pattern),
            market_status_label=market_status_label(market_context.get('market_status')),
            external_market_status_label=market_status_label(external_market_context.get('status')),
            chart_url=f"https://finance.naver.com/item/fchart.naver?code={str(row.get('stock_code', '')).zfill(6)}",
            **dict(zip(
                ('nxt_eligible', 'recommended_window', 'recommended_order_type'),
                self._nxt_plan(str(row.get('stock_code', ''))),
            )),
        )

    def _candidate_sort_key(self, row: dict[str, Any]) -> tuple[int, int, int, str]:
        return (
            -safe_int(row.get('score_total'), 0),
            safe_int(row.get('signal_rank'), 9999),
            -safe_int(row.get('trading_value'), 0),
            str(row.get('stock_code', '') or ''),
        )

    # 이 메서드는 종가배팅 화면 전체 응답을 반환한다.
    def get_closing_bet(self, date_arg: str | None, grade_filter: str, query: str, page: int, page_size: int) -> ClosingBetResponse:
        request_date = normalize_date_arg(date_arg)
        bundle = self.repository.fetch_closing_bundle(date_arg, grade_filter, query, page, page_size, featured_limit=FEATURED_PICK_LIMIT)
        run_meta = bundle['run_meta']
        basis = self._build_basis(request_date, run_meta)
        runtime_meta = run_meta.get('runtime_meta') if isinstance(run_meta, dict) and isinstance(run_meta.get('runtime_meta'), dict) else {}
        fallback_external_context = runtime_meta.get('external_market_context') if isinstance(runtime_meta.get('external_market_context'), dict) else {}
        selected_date = basis.selected_date
        is_today = selected_date == datetime.now(timezone.utc).date().isoformat()

        aggregate = bundle['aggregate']
        total = safe_int(aggregate.get('total'), 0)
        grade_counts = {
            'S': safe_int(aggregate.get('grade_s'), 0),
            'A': safe_int(aggregate.get('grade_a'), 0),
            'B': safe_int(aggregate.get('grade_b'), 0),
            'C': safe_int(aggregate.get('grade_c'), 0),
        }
        signals_count = safe_int(aggregate.get('signals_count'), 0)
        featured_candidates = []
        seen_featured: set[str] = set()
        for row in sorted([*list(bundle['featured_rows']), *list(bundle['page_rows'])], key=self._candidate_sort_key):
            resolved_grade = infer_signal_grade(row.get('score_total'), row.get('trading_value'), row.get('change_pct'))
            code = str(row.get('stock_code', '') or '')
            if resolved_grade not in {'S', 'A', 'B'} or not code or code in seen_featured:
                continue
            featured_candidates.append(row)
            seen_featured.add(code)
            if len(featured_candidates) >= FEATURED_PICK_LIMIT:
                break
        featured_source_rows = featured_candidates
        featured_items = [self._to_item(row, fallback_external_context) for row in featured_source_rows]
        featured_codes = {str(row.get('stock_code', '') or '') for row in featured_source_rows}
        page_items = [
            self._to_item(row, fallback_external_context)
            for row in bundle['page_rows']
            if str(row.get('stock_code', '') or '') not in featured_codes
        ]
        pagination_total = safe_int(bundle.get('list_total'), 0)
        safe_page = safe_int(bundle.get('page'), 1)
        total_pages = safe_int(bundle.get('total_pages'), 0)

        return ClosingBetResponse(
            date=selected_date,
            is_today=is_today,
            status='UPDATED' if is_today else 'OLD_DATA',
            candidates_count=total,
            signals_count=signals_count,
            buyable_signals_count=signals_count,
            featured_count=len(featured_items),
            grade_counts=grade_counts,
            featured_items=featured_items,
            items=page_items,
            pagination=PaginationPayload(page=safe_page, page_size=page_size, total=pagination_total, total_pages=total_pages),
            filters={'grade': grade_filter, 'q': str(query or '')},
            basis=basis,
        )

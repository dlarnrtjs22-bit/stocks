from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from batch.runtime_source.providers.kiwoom_client import KiwoomAPIError, KiwoomRESTClient, venue_stock_code
from backend.app.repositories.read_repository import ReadRepository
from backend.app.schemas.closing_bet import PaginationPayload
from backend.app.schemas.performance import (
    GradeSummaryItem,
    PerformanceComparison,
    PerformanceRefreshResponse,
    PerformanceResponse,
    PerformanceSummary,
    PerformanceTradeItem,
)
from backend.app.services.closing_bet_service import ClosingBetService
from backend.app.services.view_helpers import infer_themes, safe_float, safe_int


SEOUL_TZ = ZoneInfo('Asia/Seoul')
TRACKED_PICK_LIMIT = 5


def _parse_kiwoom_quote_time(eval_date: date, raw_value: str) -> datetime | None:
    digits = ''.join(ch for ch in str(raw_value or '') if ch.isdigit())
    if len(digits) >= 14:
        try:
            parsed = datetime.strptime(digits[:14], '%Y%m%d%H%M%S')
            return parsed.replace(tzinfo=SEOUL_TZ)
        except ValueError:
            pass
    if len(digits) >= 12:
        try:
            parsed = datetime.strptime(digits[:12], '%Y%m%d%H%M')
            return parsed.replace(tzinfo=SEOUL_TZ)
        except ValueError:
            pass
    if len(digits) < 6:
        return None
    try:
        return datetime.combine(
            eval_date,
            time(int(digits[0:2]), int(digits[2:4]), int(digits[4:6])),
            tzinfo=SEOUL_TZ,
        )
    except ValueError:
        return None


def _resolve_date_range(date_from_arg: str | None, date_to_arg: str | None) -> tuple[date, date, str]:
    today = datetime.now(SEOUL_TZ).date()
    date_from = date.fromisoformat(str(date_from_arg).strip()) if date_from_arg else today - timedelta(days=6)
    date_to = date.fromisoformat(str(date_to_arg).strip()) if date_to_arg else today
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to, f'{date_from.isoformat()}~{date_to.isoformat()}'


class PerformanceService:
    def __init__(self, repository: ReadRepository | None = None) -> None:
        self.repository = repository or ReadRepository()
        self.closing_service = ClosingBetService(self.repository)

    def _top_featured_picks(self, date_arg: str | None) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
        run_meta = self.repository.fetch_run_meta(date_arg)
        if not run_meta:
            return None, []
        closing = self.closing_service.get_closing_bet(date_arg, 'ALL', '', 1, 8)
        featured = [item.model_dump() for item in closing.featured_items]
        return run_meta, featured[:TRACKED_PICK_LIMIT]

    def _fetch_slot_quote(
        self,
        client: KiwoomRESTClient,
        *,
        ticker: str,
        eval_date: date,
        venue: str,
        slot_hour: int,
    ) -> tuple[float, datetime | None] | None:
        body = client.request(
            '/api/dostk/chart',
            'ka10080',
            {
                'stk_cd': venue_stock_code(ticker, venue),
                'tic_scope': '5',
                'upd_stkpc_tp': '1',
                'base_dt': eval_date.strftime('%Y%m%d'),
            },
        ).body
        rows = body.get('stk_min_pole_chart_qry') if isinstance(body.get('stk_min_pole_chart_qry'), list) else []
        for item in reversed(rows):
            quote_time = _parse_kiwoom_quote_time(eval_date, str(item.get('cntr_tm', '') or ''))
            if quote_time is None or quote_time.date() != eval_date or quote_time.hour != slot_hour:
                continue
            price = abs(safe_float(item.get('cur_prc'), 0.0))
            if price <= 0:
                continue
            return price, quote_time
        return None

    def quick_refresh(self, date_from_arg: str | None, date_to_arg: str | None) -> PerformanceRefreshResponse:
        date_from, date_to, _ = _resolve_date_range(date_from_arg, date_to_arg)
        run_dates = self.repository.list_run_dates_between(date_from, date_to)
        if not run_dates:
            return PerformanceRefreshResponse(status='no_run', message='선택한 날짜의 run 이 없습니다.')

        tracked_count = 0
        for run_day in run_dates:
            run_meta, picks = self._top_featured_picks(run_day.isoformat())
            if not run_meta:
                continue
            tracked_count += self.repository.replace_tracked_picks(run_meta, picks)
        tracked_rows = self.repository.fetch_tracked_pick_rows_between(date_from, date_to)
        if not tracked_rows:
            return PerformanceRefreshResponse(status='no_picks', tracked_count=tracked_count, message='저장된 추적 종목이 없습니다.')

        now_kst = datetime.now(SEOUL_TZ)
        refreshed_08 = 0
        refreshed_09 = 0
        skipped_08 = 0
        skipped_09 = 0
        client = KiwoomRESTClient()

        for row in tracked_rows:
            tracked_id = safe_int(row.get('tracked_id'), 0)
            ticker = str(row.get('stock_code', '')).zfill(6)
            run_date = row.get('run_date')
            if not tracked_id or not ticker or not isinstance(run_date, date):
                continue

            eval_date = self.repository.next_trade_date(run_date, ticker)
            if eval_date is None and now_kst.date() > run_date:
                eval_date = now_kst.date()
            if eval_date is None:
                skipped_08 += 1
                skipped_09 += 1
                continue

            if self.repository.has_compare_price(tracked_id, eval_date, '08'):
                skipped_08 += 1
            else:
                try:
                    quote_08 = self._fetch_slot_quote(client, ticker=ticker, eval_date=eval_date, venue='NXT', slot_hour=8)
                except KiwoomAPIError:
                    quote_08 = None
                if quote_08 is None:
                    skipped_08 += 1
                else:
                    price, quote_time = quote_08
                    self.repository.upsert_compare_price(
                        tracked_id=tracked_id,
                        eval_date=eval_date,
                        eval_slot='08',
                        venue='NXT',
                        price=price,
                        quote_time=quote_time,
                    )
                    refreshed_08 += 1

            if self.repository.has_compare_price(tracked_id, eval_date, '09'):
                skipped_09 += 1
            else:
                try:
                    quote_09 = self._fetch_slot_quote(client, ticker=ticker, eval_date=eval_date, venue='KRX', slot_hour=9)
                except KiwoomAPIError:
                    quote_09 = None
                if quote_09 is None:
                    open_price = self.repository.get_open_price(ticker, eval_date)
                    if open_price is None:
                        skipped_09 += 1
                    else:
                        self.repository.upsert_compare_price(
                            tracked_id=tracked_id,
                            eval_date=eval_date,
                            eval_slot='09',
                            venue='KRX_OPEN',
                            price=open_price,
                            quote_time=datetime.combine(eval_date, time(9, 0), tzinfo=SEOUL_TZ),
                        )
                        refreshed_09 += 1
                else:
                    price, quote_time = quote_09
                    self.repository.upsert_compare_price(
                        tracked_id=tracked_id,
                        eval_date=eval_date,
                        eval_slot='09',
                        venue='KRX',
                        price=price,
                        quote_time=quote_time,
                    )
                    refreshed_09 += 1

        return PerformanceRefreshResponse(
            status='ok',
            tracked_count=tracked_count,
            refreshed_08=refreshed_08,
            refreshed_09=refreshed_09,
            skipped_08=skipped_08,
            skipped_09=skipped_09,
            message='추적 상위 5종목 비교값을 갱신했습니다.',
        )

    def get_performance(self, date_from_arg: str | None, date_to_arg: str | None, grade_filter: str, outcome_filter: str, query: str, page: int, page_size: int) -> PerformanceResponse:
        date_from, date_to, request_date = _resolve_date_range(date_from_arg, date_to_arg)
        bundle = self.repository.fetch_performance_bundle(date_from, date_to, grade_filter, outcome_filter, query, page, page_size)
        run_meta = bundle['run_meta']
        basis = self.closing_service._build_basis(request_date, run_meta)
        selected_date = basis.selected_date
        is_today = selected_date == datetime.now(timezone.utc).date().isoformat()

        trades: list[PerformanceTradeItem] = []
        for row in bundle['page_rows']:
            grade = str(row.get('grade', 'C'))
            roi = round(safe_float(row.get('roi_09'), 0.0), 2) if row.get('roi_09') is not None else 0.0
            outcome = str(row.get('outcome_09', 'OPEN'))
            code = str(row.get('stock_code', '')).zfill(6)
            name = str(row.get('stock_name', ''))
            buy_date = row.get('signal_date').isoformat() if row.get('signal_date') else selected_date
            roi_08 = round(safe_float(row.get('roi_08'), 0.0), 2) if row.get('roi_08') is not None else None
            roi_09 = round(safe_float(row.get('roi_09'), 0.0), 2) if row.get('roi_09') is not None else None
            trades.append(
                PerformanceTradeItem(
                    key=safe_int(row.get('tracked_id'), safe_int(row.get('signal_rank'), 0)),
                    date=buy_date,
                    buy_date=buy_date,
                    grade=grade,
                    name=name,
                    ticker=code,
                    entry=round(safe_float(row.get('entry_price'), 0.0), 2),
                    outcome=outcome,
                    roi=roi,
                    max_high=max([value for value in [roi_08, roi_09] if value is not None], default=0.0),
                    price_trail='UP' if roi_09 and roi_09 > 0 else 'DOWN' if roi_09 and roi_09 < 0 else '-',
                    days=0 if outcome == 'OPEN' else 1,
                    score=safe_int(row.get('score_total'), 0),
                    themes=infer_themes(name),
                    eval_date=row.get('eval_date').isoformat() if row.get('eval_date') else None,
                    eval_08_price=round(safe_float(row.get('eval_08_price'), 0.0), 2) if row.get('eval_08_price') is not None else None,
                    eval_08_time=row.get('eval_08_time').isoformat() if row.get('eval_08_time') else None,
                    eval_08_venue=str(row.get('eval_08_venue') or '') or None,
                    outcome_08=str(row.get('outcome_08') or 'OPEN'),
                    roi_08=roi_08,
                    eval_09_price=round(safe_float(row.get('eval_09_price'), 0.0), 2) if row.get('eval_09_price') is not None else None,
                    eval_09_time=row.get('eval_09_time').isoformat() if row.get('eval_09_time') else None,
                    eval_09_venue=str(row.get('eval_09_venue') or '') or None,
                    outcome_09=str(row.get('outcome_09') or 'OPEN'),
                    roi_09=roi_09,
                )
            )

        summary_row = bundle['summary']
        wins = safe_int(summary_row.get('wins'), 0)
        losses = safe_int(summary_row.get('losses'), 0)
        opens = safe_int(summary_row.get('open'), 0)
        closed = wins + losses
        avg_roi = round(safe_float(summary_row.get('avg_roi'), 0.0), 2)
        total_roi = round(safe_float(summary_row.get('total_roi'), 0.0), 2)
        profit_factor = round(safe_float(summary_row.get('profit_factor'), 0.0), 2)
        avg_days = round(safe_float(summary_row.get('avg_days'), 0.0), 2)

        grade_summary: list[GradeSummaryItem] = []
        grade_map = {str(item.get('grade', '')): item for item in bundle['grade_rows']}
        for grade in ['S', 'A', 'B', 'C']:
            grade_row = grade_map.get(grade, {})
            grade_wins = safe_int(grade_row.get('wins'), 0)
            grade_losses = safe_int(grade_row.get('losses'), 0)
            grade_summary.append(
                GradeSummaryItem(
                    grade=grade,
                    count=safe_int(grade_row.get('count'), 0),
                    win_rate=round(safe_float(grade_row.get('win_rate'), 0.0), 2),
                    avg_roi=round(safe_float(grade_row.get('avg_roi'), 0.0), 2),
                    wl=f'{grade_wins}/{grade_losses}',
                    win_rate_08=round(safe_float(grade_row.get('win_rate_08'), 0.0), 2),
                    avg_roi_08=round(safe_float(grade_row.get('avg_roi_08'), 0.0), 2),
                    wl_08=str(grade_row.get('wl_08') or '0/0'),
                    win_rate_09=round(safe_float(grade_row.get('win_rate_09'), 0.0), 2),
                    avg_roi_09=round(safe_float(grade_row.get('avg_roi_09'), 0.0), 2),
                    wl_09=str(grade_row.get('wl_09') or '0/0'),
                )
            )

        total = safe_int(summary_row.get('total_signals'), 0)
        safe_page = safe_int(bundle.get('page'), 1)
        total_pages = safe_int(bundle.get('total_pages'), 0)

        return PerformanceResponse(
            date=selected_date,
            is_today=is_today,
            summary=PerformanceSummary(
                total_signals=total,
                win_rate=round((wins / closed * 100) if closed else 0.0, 2),
                wins=wins,
                losses=losses,
                open=opens,
                avg_roi=avg_roi,
                total_roi=total_roi,
                profit_factor=profit_factor,
                avg_days=avg_days,
            ),
            summary_08=PerformanceSummary(**bundle.get('summary_08', {})),
            summary_09=PerformanceSummary(**bundle.get('summary_09', {})),
            comparison=PerformanceComparison(**bundle.get('comparison', {})),
            grade_summary=grade_summary,
            distribution={'wins': wins, 'open': opens, 'losses': losses},
            trades=trades,
            pagination=PaginationPayload(page=safe_page, page_size=page_size, total=total, total_pages=total_pages),
            basis=basis,
        )

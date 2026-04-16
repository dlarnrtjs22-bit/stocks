from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from batch.runtime_source.providers.kiwoom_client import KiwoomRESTClient, effective_venue, venue_stock_code
from backend.app.repositories.dashboard_repository import DashboardRepository
from backend.app.schemas.dashboard import DashboardAccountPayload, DashboardAccountPosition
from backend.app.schemas.trade_history import TradeHistoryDailyItem, TradeHistoryExecutionItem, TradeHistoryResponse
from backend.app.services.view_helpers import safe_float, safe_int


SEOUL_TZ = ZoneInfo('Asia/Seoul')


def _resolve_date_range(date_from_arg: str | None, date_to_arg: str | None) -> tuple[date, date]:
    today = datetime.now(SEOUL_TZ).date()
    date_from = date.fromisoformat(str(date_from_arg).strip()) if date_from_arg else today - timedelta(days=6)
    date_to = date.fromisoformat(str(date_to_arg).strip()) if date_to_arg else today
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def _parse_hhmmss_on_date(base_date: date, raw_value: str) -> datetime | None:
    digits = ''.join(ch for ch in str(raw_value or '') if ch.isdigit())
    if len(digits) < 6:
        return None
    try:
        return datetime.combine(
            base_date,
            time(int(digits[0:2]), int(digits[2:4]), int(digits[4:6])),
            tzinfo=SEOUL_TZ,
        )
    except ValueError:
        return None


def _normalize_ticker(value: str | None) -> str:
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits.zfill(6) if digits else ''


def _infer_side(order_type: str) -> str:
    text = str(order_type or '')
    if '매수' in text:
        return 'BUY'
    if '매도' in text:
        return 'SELL'
    return 'ALL'


def _calc_slippage_bps(order_type: str, order_price: float, filled_price: float) -> float:
    if order_price <= 0 or filled_price <= 0:
        return 0.0
    side = _infer_side(order_type)
    if side == 'SELL':
        return round(((order_price - filled_price) / order_price) * 10000.0, 2)
    return round(((filled_price - order_price) / order_price) * 10000.0, 2)


def _signed_abs_int(value: int) -> int:
    return int(value) if value >= 0 else -int(abs(value))


class TradeHistoryService:
    def __init__(self, repository: DashboardRepository | None = None) -> None:
        self.repository = repository or DashboardRepository()

    def _sync_account_snapshot(self, client: KiwoomRESTClient) -> tuple[str, DashboardAccountPayload]:
        account_info = client.request('/api/dostk/acnt', 'ka00001', {}).body
        account_no = str(account_info.get('acctNo', '') or '').strip()
        snapshot_body = client.request('/api/dostk/acnt', 'kt00018', {'qry_tp': '1', 'dmst_stex_tp': 'KRX'}).body
        positions_raw = snapshot_body.get('acnt_evlt_remn_indv_tot') if isinstance(snapshot_body.get('acnt_evlt_remn_indv_tot'), list) else []

        positions_payload: list[dict[str, object]] = []
        account_positions: list[DashboardAccountPosition] = []
        for item in positions_raw:
            if not isinstance(item, dict):
                continue
            ticker = _normalize_ticker(item.get('stk_cd'))
            if not ticker:
                continue
            avg_price = abs(safe_float(item.get('pur_pric')))
            current_price = abs(safe_float(item.get('cur_prc')))
            eval_amount = abs(safe_int(item.get('evlt_amt')))
            profit_amount = safe_int(item.get('evltv_prft'))
            profit_rate = safe_float(item.get('prft_rt'))
            quantity = abs(safe_int(item.get('rmnd_qty')))
            available_qty = abs(safe_int(item.get('trde_able_qty')))
            positions_payload.append(
                {
                    'ticker': ticker,
                    'stock_name': str(item.get('stk_nm', '') or ''),
                    'quantity': quantity,
                    'available_qty': available_qty,
                    'avg_price': avg_price,
                    'current_price': current_price,
                    'eval_amount': eval_amount,
                    'profit_amount': profit_amount,
                    'profit_rate': profit_rate,
                }
            )
            account_positions.append(
                DashboardAccountPosition(
                    ticker=ticker,
                    stock_name=str(item.get('stk_nm', '') or ''),
                    quantity=quantity,
                    available_qty=available_qty,
                    avg_price=avg_price,
                    current_price=current_price,
                    eval_amount=eval_amount,
                    profit_amount=profit_amount,
                    profit_rate=profit_rate,
                )
            )

        old_total_eval_amt = abs(safe_int(snapshot_body.get('tot_evlt_amt')))
        old_estimated_assets = abs(safe_int(snapshot_body.get('prsm_dpst_aset_amt')))
        cash_component = old_estimated_assets - old_total_eval_amt
        venue, _ = effective_venue()
        live_updated = False

        for index, position in enumerate(positions_payload):
            ticker = str(position.get('ticker', '') or '')
            avg_price = abs(safe_float(position.get('avg_price')))
            quantity = abs(safe_int(position.get('quantity')))
            if not ticker or avg_price <= 0 or quantity <= 0:
                continue
            try:
                quote = client.request('/api/dostk/stkinfo', 'ka10001', {'stk_cd': venue_stock_code(ticker, venue)}).body
            except Exception:
                continue

            live_price = abs(safe_float(quote.get('cur_prc')))
            if live_price <= 0:
                continue

            live_eval_amount = int(round(live_price * quantity))
            live_profit_amount = _signed_abs_int(live_eval_amount - int(round(avg_price * quantity)))
            live_profit_rate = round(((live_price - avg_price) / avg_price) * 100.0, 2)

            positions_payload[index]['current_price'] = live_price
            positions_payload[index]['eval_amount'] = live_eval_amount
            positions_payload[index]['profit_amount'] = live_profit_amount
            positions_payload[index]['profit_rate'] = live_profit_rate

            account_positions[index].current_price = live_price
            account_positions[index].eval_amount = live_eval_amount
            account_positions[index].profit_amount = live_profit_amount
            account_positions[index].profit_rate = live_profit_rate
            live_updated = True

        total_purchase_amt = abs(safe_int(snapshot_body.get('tot_pur_amt')))
        total_eval_amt = sum(abs(safe_int(item.get('eval_amount'))) for item in positions_payload)
        total_eval_profit = sum(safe_int(item.get('profit_amount')) for item in positions_payload)
        total_profit_rate = round((total_eval_profit / total_purchase_amt) * 100.0, 2) if total_purchase_amt > 0 else 0.0
        estimated_assets = max(0, cash_component + total_eval_amt)

        snapshot_payload = {
            'account_no': account_no,
            'snapshot_time': datetime.now(SEOUL_TZ).isoformat(),
            'venue': venue,
            'total_purchase_amt': total_purchase_amt,
            'total_eval_amt': total_eval_amt,
            'total_eval_profit': total_eval_profit,
            'total_profit_rate': total_profit_rate,
            'estimated_assets': estimated_assets,
            'holdings_count': len(account_positions),
            'realized_profit': 0,
            'unfilled_count': 0,
            'total_unfilled_qty': 0,
            'avg_fill_latency_ms': 0.0,
            'est_slippage_bps': 0.0,
            'raw_payload': snapshot_body,
        }
        self.repository.save_account_snapshot(snapshot_payload)
        self.repository.replace_account_positions(account_no, positions_payload)

        account = DashboardAccountPayload(
            available=True,
            account_no=account_no,
            snapshot_time=str(snapshot_payload['snapshot_time']),
            venue=venue,
            total_purchase_amt=total_purchase_amt,
            total_eval_amt=total_eval_amt,
            total_eval_profit=total_eval_profit,
            total_profit_rate=total_profit_rate,
            estimated_assets=estimated_assets,
            holdings_count=len(account_positions),
            realized_profit=0,
            unfilled_count=0,
            total_unfilled_qty=0,
            avg_fill_latency_ms=0.0,
            est_slippage_bps=0.0,
            note=f'계좌 API 동기화 완료: 계좌 {account_no}, 보유 {len(account_positions)}건, 시세 {venue} 기준{"(실시간 반영)" if live_updated else ""}',
            positions=account_positions,
        )
        return account_no, account

    def _sync_today_executions(self, client: KiwoomRESTClient, account_no: str) -> int:
        body = client.request('/api/dostk/acnt', 'ka10076', {'qry_tp': '0', 'sell_tp': '0', 'stex_tp': '0'}).body
        rows = body.get('cntr') if isinstance(body.get('cntr'), list) else []
        today = datetime.now(SEOUL_TZ).date()
        events: list[dict[str, object]] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            order_type = str(item.get('io_tp_nm', '') or '')
            order_price = abs(safe_float(item.get('ord_pric')))
            filled_price = abs(safe_float(item.get('cntr_pric')))
            order_time = _parse_hhmmss_on_date(today, str(item.get('ord_tm', '') or ''))
            events.append(
                {
                    'account_no': account_no,
                    'order_no': str(item.get('ord_no', '') or '').strip(),
                    'ticker': _normalize_ticker(item.get('stk_cd')),
                    'stock_name': str(item.get('stk_nm', '') or ''),
                    'order_type': order_type,
                    'order_status': str(item.get('ord_stt', '') or ''),
                    'order_qty': abs(safe_int(item.get('ord_qty'))),
                    'filled_qty': abs(safe_int(item.get('cntr_qty'))),
                    'unfilled_qty': abs(safe_int(item.get('oso_qty'))),
                    'order_price': order_price,
                    'filled_price': filled_price,
                    'order_time': order_time,
                    'filled_time': order_time,
                    'fill_latency_ms': 0.0,
                    'slippage_bps': _calc_slippage_bps(order_type, order_price, filled_price),
                    'venue': str(item.get('stex_tp_txt', item.get('stex_tp', '')) or ''),
                    'raw_payload': item,
                }
            )
        return self.repository.upsert_order_execution_events(events)

    def _load_daily_realized(self, client: KiwoomRESTClient, date_from: date, date_to: date) -> list[TradeHistoryDailyItem]:
        body = client.request(
            '/api/dostk/acnt',
            'ka10074',
            {
                'strt_dt': date_from.strftime('%Y%m%d'),
                'end_dt': date_to.strftime('%Y%m%d'),
            },
        ).body
        rows = body.get('dt_rlzt_pl') if isinstance(body.get('dt_rlzt_pl'), list) else []
        items: list[TradeHistoryDailyItem] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            raw_date = str(item.get('dt', '') or '').strip()
            formatted = f'{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}' if len(raw_date) == 8 else raw_date
            items.append(
                TradeHistoryDailyItem(
                    date=formatted,
                    buy_amount=abs(safe_int(item.get('buy_amt'))),
                    sell_amount=abs(safe_int(item.get('sell_amt'))),
                    realized_profit=safe_int(item.get('tdy_sel_pl')),
                    commission=abs(safe_int(item.get('tdy_trde_cmsn'))),
                    tax=abs(safe_int(item.get('tdy_trde_tax'))),
                )
            )
        return items

    def _load_cached_account(self) -> tuple[str, DashboardAccountPayload]:
        snapshot = self.repository.fetch_account_snapshot()
        account_no = str(snapshot.get('account_no', '') or '').strip() if snapshot else ''
        position_rows = self.repository.fetch_account_positions(account_no if account_no else None)
        positions = [
            DashboardAccountPosition(
                ticker=str(row.get('ticker', '')).zfill(6),
                stock_name=str(row.get('stock_name', '') or ''),
                quantity=safe_int(row.get('quantity')),
                available_qty=safe_int(row.get('available_qty')),
                avg_price=safe_float(row.get('avg_price')),
                current_price=safe_float(row.get('current_price')),
                eval_amount=safe_int(row.get('eval_amount')),
                profit_amount=safe_int(row.get('profit_amount')),
                profit_rate=safe_float(row.get('profit_rate')),
            )
            for row in position_rows
        ]
        if not snapshot:
            return '', DashboardAccountPayload(note='계좌 저장 데이터가 없습니다.', positions=positions)

        return account_no, DashboardAccountPayload(
            available=True,
            account_no=account_no,
            snapshot_time=snapshot.get('snapshot_time').isoformat() if hasattr(snapshot.get('snapshot_time'), 'isoformat') else None,
            venue=str(snapshot.get('venue', '') or ''),
            total_purchase_amt=safe_int(snapshot.get('total_purchase_amt')),
            total_eval_amt=safe_int(snapshot.get('total_eval_amt')),
            total_eval_profit=safe_int(snapshot.get('total_eval_profit')),
            total_profit_rate=safe_float(snapshot.get('total_profit_rate')),
            estimated_assets=safe_int(snapshot.get('estimated_assets')),
            holdings_count=safe_int(snapshot.get('holdings_count')),
            realized_profit=safe_int(snapshot.get('realized_profit')),
            unfilled_count=safe_int(snapshot.get('unfilled_count')),
            total_unfilled_qty=safe_int(snapshot.get('total_unfilled_qty')),
            avg_fill_latency_ms=safe_float(snapshot.get('avg_fill_latency_ms')),
            est_slippage_bps=safe_float(snapshot.get('est_slippage_bps')),
            note='계좌 API 조회에 실패해 마지막 저장값을 표시합니다.',
            positions=positions,
        )

    def get_trade_history(
        self,
        *,
        date_from_arg: str | None,
        date_to_arg: str | None,
        side_filter: str,
        status_filter: str,
        query: str,
    ) -> TradeHistoryResponse:
        date_from, date_to = _resolve_date_range(date_from_arg, date_to_arg)
        try:
            client = KiwoomRESTClient()
            account_no, account = self._sync_account_snapshot(client)
            self._sync_today_executions(client, account_no)
            daily_summary = self._load_daily_realized(client, date_from, date_to)
        except Exception as exc:
            account_no, account = self._load_cached_account()
            daily_summary = []
            account.note = f'{account.note} ({exc})'.strip()

        normalized_side = str(side_filter or 'ALL').strip().upper()
        if normalized_side not in {'ALL', 'BUY', 'SELL'}:
            normalized_side = 'ALL'
        normalized_status = str(status_filter or 'ALL').strip().upper()
        query_text = str(query or '').strip().lower()

        execution_rows = self.repository.fetch_order_execution_events(
            account_no=account_no,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
        )
        executions: list[TradeHistoryExecutionItem] = []
        for row in execution_rows:
            raw_payload = row.get('raw_payload') if isinstance(row.get('raw_payload'), dict) else {}
            order_type = str(row.get('order_type', '') or '')
            side = _infer_side(order_type)
            status = str(row.get('order_status', '') or '')
            ticker = _normalize_ticker(row.get('ticker'))
            stock_name = str(row.get('stock_name', '') or '')
            order_no = str(row.get('order_no', '') or '')

            if normalized_side != 'ALL' and side != normalized_side:
                continue
            if normalized_status != 'ALL' and status.upper() != normalized_status:
                continue
            if query_text and query_text not in ticker.lower() and query_text not in stock_name.lower() and query_text not in order_no.lower():
                continue

            executions.append(
                TradeHistoryExecutionItem(
                    key=f"{account_no}:{order_no}",
                    order_no=order_no,
                    original_order_no=str(raw_payload.get('orig_ord_no', '') or '').strip() or None,
                    ticker=ticker,
                    stock_name=stock_name,
                    side=side,
                    order_type=order_type,
                    order_status=status,
                    trade_type=str(raw_payload.get('trde_tp', '') or ''),
                    venue=str(row.get('venue', '') or ''),
                    order_qty=safe_int(row.get('order_qty')),
                    filled_qty=safe_int(row.get('filled_qty')),
                    unfilled_qty=safe_int(row.get('unfilled_qty')),
                    order_price=safe_float(row.get('order_price')),
                    filled_price=safe_float(row.get('filled_price')),
                    order_time=row.get('order_time').isoformat() if hasattr(row.get('order_time'), 'isoformat') else None,
                    filled_time=row.get('filled_time').isoformat() if hasattr(row.get('filled_time'), 'isoformat') else None,
                    fee=abs(safe_int(raw_payload.get('tdy_trde_cmsn'))),
                    tax=abs(safe_int(raw_payload.get('tdy_trde_tax'))),
                    stop_price=safe_float(raw_payload.get('stop_pric')),
                    sor_yn=str(raw_payload.get('sor_yn', '') or ''),
                    fill_latency_ms=safe_float(row.get('fill_latency_ms')),
                    slippage_bps=safe_float(row.get('slippage_bps')),
                )
            )

        account.realized_profit = sum(item.realized_profit for item in daily_summary)
        account.unfilled_count = sum(1 for item in executions if item.unfilled_qty > 0)
        account.total_unfilled_qty = sum(item.unfilled_qty for item in executions)
        account.note = f'{account.note} / 체결 {len(executions)}건'

        return TradeHistoryResponse(
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            account=account,
            daily_summary=daily_summary,
            executions=executions,
            filters={
                'side': normalized_side,
                'status': normalized_status,
                'q': query_text,
            },
            refreshed_at=datetime.now(SEOUL_TZ).isoformat(),
        )

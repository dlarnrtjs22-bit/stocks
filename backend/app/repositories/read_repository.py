from __future__ import annotations

# 이 파일은 종가배팅과 누적 성과 화면이 공통으로 사용하는 조회 전용 repository 이다.
import json
from datetime import date
from typing import Any

from backend.app.core.database import db_connection


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _roi(entry_price: Any, exit_price: Any) -> float | None:
    entry = abs(_safe_float(entry_price, 0.0))
    exit_value = abs(_safe_float(exit_price, 0.0))
    if entry <= 0 or exit_value <= 0:
        return None
    return round(((exit_value - entry) / entry) * 100.0, 2)


def _outcome(roi: float | None) -> str:
    if roi is None:
        return 'OPEN'
    if roi > 0:
        return 'WIN'
    if roi < 0:
        return 'LOSS'
    return 'OPEN'


def _summary_for(rows: list[dict[str, Any]], roi_key: str, outcome_key: str) -> dict[str, Any]:
    wins = sum(1 for row in rows if row.get(outcome_key) == 'WIN')
    losses = sum(1 for row in rows if row.get(outcome_key) == 'LOSS')
    opens = sum(1 for row in rows if row.get(outcome_key) == 'OPEN')
    closed = wins + losses
    rois = [_safe_float(row.get(roi_key), 0.0) for row in rows if row.get(roi_key) is not None]
    positive = sum(value for value in rois if value > 0)
    negative = sum(value for value in rois if value < 0)
    return {
        'total_signals': len(rows),
        'wins': wins,
        'losses': losses,
        'open': opens,
        'win_rate': round((wins / closed * 100.0) if closed else 0.0, 2),
        'avg_roi': round((sum(rois) / len(rois)) if rois else 0.0, 2),
        'total_roi': round(sum(rois), 2),
        'profit_factor': round((positive / abs(negative)) if negative else 0.0, 2),
        'avg_days': round((closed / len(rows)) if rows else 0.0, 2),
    }


def _grade_summary_for(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grade_rows: list[dict[str, Any]] = []
    for grade in ['S', 'A', 'B', 'C']:
        grade_items = [row for row in rows if str(row.get('grade', 'C')) == grade]
        summary_08 = _summary_for(grade_items, 'roi_08', 'outcome_08')
        summary_09 = _summary_for(grade_items, 'roi_09', 'outcome_09')
        grade_rows.append(
            {
                'grade': grade,
                'count': len(grade_items),
                'wins': summary_09['wins'],
                'losses': summary_09['losses'],
                'win_rate': summary_09['win_rate'],
                'avg_roi': summary_09['avg_roi'],
                'wl': f"{summary_09['wins']}/{summary_09['losses']}",
                'win_rate_08': summary_08['win_rate'],
                'avg_roi_08': summary_08['avg_roi'],
                'wl_08': f"{summary_08['wins']}/{summary_08['losses']}",
                'win_rate_09': summary_09['win_rate'],
                'avg_roi_09': summary_09['avg_roi'],
                'wl_09': f"{summary_09['wins']}/{summary_09['losses']}",
            }
        )
    return grade_rows


# 이 함수는 latest 또는 특정 날짜 문자열을 SQL 파라미터로 바꾼다.
def _normalize_run_date(date_arg: str | None) -> date | None:
    if not date_arg or str(date_arg).strip().lower() == 'latest':
        return None
    return date.fromisoformat(str(date_arg).strip())


# 이 함수는 등급 필터를 허용된 값으로 정규화한다.
def _normalize_grade_filter(grade_filter: str) -> str:
    target = str(grade_filter or 'ALL').strip().upper()
    return target if target in {'ALL', 'S', 'A', 'B', 'C'} else 'ALL'


# 이 함수는 검색어를 SQL like 파라미터 형태로 바꾼다.
def _normalize_keyword(query: str) -> tuple[str, str]:
    keyword = str(query or '').strip().lower()
    return keyword, f'%{keyword}%'


# 이 함수는 JSONB 집계 결과를 항상 파이썬 list 로 맞춘다.
def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


# 이 repository 는 조회 화면에서 필요한 데이터를 SQL 한 번으로 읽는 데 집중한다.
class ReadRepository:
    # 이 메서드는 사용 가능한 run 날짜 목록을 최신순으로 반환한다.
    def list_run_dates(self) -> list[str]:
        sql = """
        select distinct run_date
        from jongga_runs
        order by run_date desc
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [row['run_date'].isoformat() for row in rows if row.get('run_date')]

    # 이 메서드는 선택한 날짜의 최신 run 메타만 조회한다.
    def fetch_run_meta(self, date_arg: str | None) -> dict[str, Any] | None:
        run_date = _normalize_run_date(date_arg)
        sql = """
        select run_id, run_date, created_at, runtime_meta, total_candidates, filtered_count
        from jongga_runs
        where (%(run_date)s::date is null or run_date = %(run_date)s::date)
        order by created_at desc
        limit 1
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'run_date': run_date})
                return cur.fetchone()

    def replace_tracked_picks(self, run_meta: dict[str, Any], picks: list[dict[str, Any]]) -> int:
        run_id = run_meta.get('run_id')
        run_date = run_meta.get('run_date')
        if not run_id or not run_date:
            return 0

        rows: list[tuple[Any, ...]] = []
        for index, item in enumerate(picks, start=1):
            rows.append(
                (
                    run_id,
                    run_date,
                    index,
                    _safe_int(item.get('global_rank', item.get('rank')), index),
                    str(item.get('ticker', '')).zfill(6),
                    str(item.get('name', '')),
                    str(item.get('market', '')),
                    str(item.get('grade', 'C')),
                    str(item.get('base_grade', item.get('grade', 'C'))),
                    abs(_safe_float(item.get('entry_price'), 0.0)),
                    _safe_int(item.get('score_total'), 0),
                )
            )

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('delete from jongga_tracked_picks where run_id = %(run_id)s', {'run_id': run_id})
                if rows:
                    cur.executemany(
                        """
                        insert into jongga_tracked_picks (
                          run_id, run_date, featured_rank, signal_rank, stock_code, stock_name, market,
                          grade, base_grade, entry_price, score_total
                        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        rows,
                    )
        return len(rows)

    def fetch_tracked_pick_rows(self, date_arg: str | None) -> list[dict[str, Any]]:
        run_date = _normalize_run_date(date_arg)
        sql = """
        with selected_run as (
          select run_id, run_date
          from jongga_runs
          where (%(run_date)s::date is null or run_date = %(run_date)s::date)
          order by created_at desc
          limit 1
        )
        select
          tp.tracked_id,
          tp.run_id,
          tp.run_date,
          tp.featured_rank,
          tp.signal_rank,
          tp.stock_code,
          tp.stock_name,
          tp.market,
          tp.grade,
          tp.base_grade,
          tp.entry_price,
          tp.score_total,
          tp.selected_at
        from selected_run sr
        join jongga_tracked_picks tp on tp.run_id = sr.run_id
        order by tp.featured_rank asc, tp.signal_rank asc
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'run_date': run_date})
                return list(cur.fetchall())

    def has_compare_price(self, tracked_id: int, eval_date: date, eval_slot: str) -> bool:
        sql = """
        select 1
        from jongga_compare_prices
        where tracked_id = %(tracked_id)s
          and eval_date = %(eval_date)s::date
          and eval_slot = %(eval_slot)s
        limit 1
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'tracked_id': tracked_id, 'eval_date': eval_date, 'eval_slot': str(eval_slot)})
                return cur.fetchone() is not None

    def next_trade_date(self, run_date: date, ticker: str) -> date | None:
        sql = """
        select min(trade_date) as eval_date
        from naver_ohlcv_1d
        where ticker = %(ticker)s
          and trade_date > %(run_date)s::date
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'ticker': str(ticker).zfill(6), 'run_date': run_date})
                row = cur.fetchone()
        return row.get('eval_date') if row else None

    def get_open_price(self, ticker: str, eval_date: date) -> float | None:
        sql = """
        select abs(open_price) as open_price
        from naver_ohlcv_1d
        where ticker = %(ticker)s
          and trade_date = %(eval_date)s::date
        limit 1
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {'ticker': str(ticker).zfill(6), 'eval_date': eval_date})
                row = cur.fetchone()
        if not row or row.get('open_price') is None:
            return None
        return abs(_safe_float(row.get('open_price'), 0.0)) or None

    def upsert_compare_price(
        self,
        *,
        tracked_id: int,
        eval_date: date,
        eval_slot: str,
        venue: str,
        price: float,
        quote_time: Any,
    ) -> None:
        sql = """
        insert into jongga_compare_prices (
          tracked_id, eval_date, eval_slot, venue, price, quote_time
        ) values (
          %(tracked_id)s, %(eval_date)s::date, %(eval_slot)s, %(venue)s, %(price)s, %(quote_time)s
        )
        on conflict (tracked_id, eval_date, eval_slot) do update
        set venue = excluded.venue,
            price = excluded.price,
            quote_time = excluded.quote_time,
            collected_at = now()
        """
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        'tracked_id': tracked_id,
                        'eval_date': eval_date,
                        'eval_slot': str(eval_slot),
                        'venue': str(venue or ''),
                        'price': abs(_safe_float(price, 0.0)),
                        'quote_time': quote_time,
                    },
                )

    # 이 메서드는 종가배팅 화면 데이터를 단일 SQL 로 반환한다.
    def fetch_closing_bundle(
        self,
        date_arg: str | None,
        grade_filter: str,
        query: str,
        page: int,
        page_size: int,
        featured_limit: int = 24,
    ) -> dict[str, Any]:
        run_date = _normalize_run_date(date_arg)
        normalized_grade = _normalize_grade_filter(grade_filter)
        keyword, keyword_like = _normalize_keyword(query)
        safe_page_size = max(1, int(page_size))
        requested_page = max(1, int(page))

        sql = """
        with selected_run as (
          select run_id, run_date, created_at, runtime_meta, total_candidates, filtered_count
          from jongga_runs
          where (%(run_date)s::date is null or run_date = %(run_date)s::date)
          order by created_at desc
          limit 1
        ),
        filtered as (
          select
            js.signal_rank,
            js.stock_code,
            js.stock_name,
            js.market,
            js.sector,
            js.signal_date,
            js.signal_time,
            js.grade,
            coalesce(js.ai_overall->>'base_grade', js.ai_overall->'meta'->'decision'->>'base_grade', js.grade) as base_grade,
            coalesce((js.score->>'news')::int, 0) as score_news,
            coalesce((js.score->>'supply')::int, 0) as score_supply,
            coalesce((js.score->>'chart')::int, 0) as score_chart,
            coalesce((js.score->>'volume')::int, 0) as score_volume,
            coalesce((js.score->>'candle')::int, 0) as score_candle,
            coalesce((js.score->>'consolidation')::int, 0) as score_consolidation,
            coalesce((js.score->>'market')::int, 0) as score_market,
            coalesce((js.score->>'program')::int, 0) as score_program,
            coalesce((js.score->>'sector')::int, 0) as score_sector,
            coalesce((js.score->>'leader')::int, 0) as score_leader,
            coalesce((js.score->>'intraday')::int, 0) as score_intraday,
            coalesce((js.score->>'news_attention')::int, 0) as score_news_attention,
            coalesce((js.score->>'total')::int, 0) as score_total,
            js.news_items,
            coalesce(flow.foreign_net_buy, 0) as foreign_1d,
            coalesce(flow.inst_net_buy, 0) as inst_1d,
            js.foreign_5d,
            js.inst_5d,
            js.individual_5d,
            js.current_price,
            js.entry_price,
            js.stop_price,
            js.target_price,
            js.r_value,
            js.position_size,
            js.quantity,
            js.r_multiplier,
            js.trading_value,
            js.change_pct,
            js.status,
            js.created_at as signal_created_at,
            coalesce(js.ai_overall->>'summary', '') as ai_summary,
            coalesce(js.ai_overall->>'status', '') as ai_status,
            coalesce(js.ai_overall->>'opinion', '') as ai_opinion,
            coalesce(js.ai_overall->'meta'->'decision'->>'status', '') as decision_status,
            coalesce(js.ai_overall->'meta'->'evidence', '[]'::jsonb) as ai_evidence,
            coalesce(js.ai_overall->'meta'->'breakdown', '{}'::jsonb) as ai_breakdown,
            coalesce(js.ai_overall->'market_context', '{}'::jsonb) as market_context,
            coalesce(js.ai_overall->'program_context', '{}'::jsonb) as program_context,
            coalesce(js.ai_overall->'sector_leadership', '{}'::jsonb) as sector_leadership,
            coalesce(js.ai_overall->'intraday_pressure', '{}'::jsonb) as intraday_pressure,
            coalesce(js.ai_overall->'news_attention', '{}'::jsonb) as news_attention,
            coalesce(js.ai_overall->'external_market_context', sr.runtime_meta->'external_market_context', '{}'::jsonb) as external_market_context,
            coalesce(js.ai_overall->'market_policy', js.ai_overall->'meta'->'decision'->'grade_policy', '{}'::jsonb) as market_policy
          from selected_run sr
          join jongga_signals js on js.run_id = sr.run_id
          left join naver_flows_1d flow
            on flow.trade_date = sr.run_date
           and flow.ticker = js.stock_code
          where (%(grade_filter)s = 'ALL' or js.grade = %(grade_filter)s)
            and (
              %(keyword)s = ''
              or lower(js.stock_code) like %(keyword_like)s
              or lower(js.stock_name) like %(keyword_like)s
            )
        ),
        stats as (
          select
            count(*)::int as total,
            coalesce(sum(case when grade in ('S', 'A', 'B') then 1 else 0 end), 0)::int as signals_count,
            coalesce(sum(case when grade = 'S' then 1 else 0 end), 0)::int as grade_s,
            coalesce(sum(case when grade = 'A' then 1 else 0 end), 0)::int as grade_a,
            coalesce(sum(case when grade = 'B' then 1 else 0 end), 0)::int as grade_b,
            coalesce(sum(case when grade = 'C' then 1 else 0 end), 0)::int as grade_c
          from filtered
        ),
        paging as (
          select
            case
              when stats.total = 0 then 1
              else least(
                greatest(%(page)s::int, 1),
                greatest(ceil(stats.total::numeric / %(page_size)s::numeric)::int, 1)
              )
            end as safe_page,
            case
              when stats.total = 0 then 0
              else greatest(ceil(stats.total::numeric / %(page_size)s::numeric)::int, 1)
            end as total_pages
          from stats
        ),
        numbered as (
          select filtered.*, row_number() over (order by filtered.signal_rank asc) as rn
          from filtered
        )
        select
          sr.run_id,
          sr.run_date,
          sr.created_at,
          sr.runtime_meta,
          sr.total_candidates,
          sr.filtered_count,
          stats.total,
          stats.signals_count,
          stats.grade_s,
          stats.grade_a,
          stats.grade_b,
          stats.grade_c,
          paging.safe_page,
          paging.total_pages,
          coalesce((
            select jsonb_agg(to_jsonb(n) - 'rn' order by n.signal_rank asc)
            from numbered n
            where n.rn <= %(featured_limit)s::int
          ), '[]'::jsonb) as featured_rows,
          coalesce((
            select jsonb_agg(to_jsonb(n) - 'rn' order by n.signal_rank asc)
            from numbered n
            cross join paging p
            where n.rn > ((p.safe_page - 1) * %(page_size)s::int)
              and n.rn <= (p.safe_page * %(page_size)s::int)
          ), '[]'::jsonb) as page_rows
        from selected_run sr
        cross join stats
        cross join paging
        """

        params = {
            'run_date': run_date,
            'grade_filter': normalized_grade,
            'keyword': keyword,
            'keyword_like': keyword_like,
            'page': requested_page,
            'page_size': safe_page_size,
            'featured_limit': max(1, int(featured_limit)),
        }
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()

        if not row:
            return {
                'run_meta': None,
                'aggregate': {'total': 0, 'signals_count': 0, 'grade_s': 0, 'grade_a': 0, 'grade_b': 0, 'grade_c': 0},
                'featured_rows': [],
                'page_rows': [],
                'page': 1,
                'total_pages': 0,
            }

        run_meta = {
            'run_id': row['run_id'],
            'run_date': row['run_date'],
            'created_at': row['created_at'],
            'runtime_meta': row.get('runtime_meta'),
            'total_candidates': row.get('total_candidates'),
            'filtered_count': row.get('filtered_count'),
        }
        aggregate = {
            'total': int(row.get('total') or 0),
            'signals_count': int(row.get('signals_count') or 0),
            'grade_s': int(row.get('grade_s') or 0),
            'grade_a': int(row.get('grade_a') or 0),
            'grade_b': int(row.get('grade_b') or 0),
            'grade_c': int(row.get('grade_c') or 0),
        }
        return {
            'run_meta': run_meta,
            'aggregate': aggregate,
            'featured_rows': _as_list(row.get('featured_rows')),
            'page_rows': _as_list(row.get('page_rows')),
            'page': int(row.get('safe_page') or 1),
            'total_pages': int(row.get('total_pages') or 0),
        }

    # 이 메서드는 누적 성과 화면 데이터를 단일 SQL 로 반환한다.
    def fetch_performance_bundle(
        self,
        date_arg: str | None,
        grade_filter: str,
        outcome_filter: str,
        query: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        run_date = _normalize_run_date(date_arg)
        normalized_grade = _normalize_grade_filter(grade_filter)
        normalized_outcome = str(outcome_filter or 'ALL').strip().upper()
        if normalized_outcome not in {'ALL', 'WIN', 'LOSS', 'OPEN'}:
            normalized_outcome = 'ALL'
        keyword, keyword_like = _normalize_keyword(query)
        safe_page_size = max(1, int(page_size))
        requested_page = max(1, int(page))

        sql = """
        with selected_run as (
          select run_id, run_date, created_at, runtime_meta, total_candidates, filtered_count
          from jongga_runs
          where (%(run_date)s::date is null or run_date = %(run_date)s::date)
          order by created_at desc
          limit 1
        )
        select
          sr.run_id,
          sr.run_date,
          sr.created_at,
          sr.runtime_meta,
          sr.total_candidates,
          sr.filtered_count,
          tp.tracked_id,
          tp.featured_rank,
          tp.signal_rank,
          tp.grade,
          tp.stock_code,
          tp.stock_name,
          abs(tp.entry_price) as entry_price,
          tp.score_total,
          eval_day.eval_date,
          cp08.price as eval_08_price,
          cp08.quote_time as eval_08_time,
          cp08.venue as eval_08_venue,
          coalesce(cp09.price, abs(ohlcv.open_price)) as eval_09_price,
          coalesce(cp09.quote_time, (eval_day.eval_date::timestamp + time '09:00')) as eval_09_time,
          case
            when cp09.price is not null then cp09.venue
            when ohlcv.open_price is not null then 'KRX_OPEN'
            else null
          end as eval_09_venue
        from selected_run sr
        join jongga_tracked_picks tp on tp.run_id = sr.run_id
        left join lateral (
          select min(candidate_date) as eval_date
          from (
            select min(cp.eval_date) as candidate_date
            from jongga_compare_prices cp
            where cp.tracked_id = tp.tracked_id
              and cp.eval_date > sr.run_date
            union
            select min(ohl.trade_date) as candidate_date
            from naver_ohlcv_1d ohl
            where ohl.ticker = tp.stock_code
              and ohl.trade_date > sr.run_date
          ) dates
          where candidate_date is not null
        ) eval_day on true
        left join jongga_compare_prices cp08
          on cp08.tracked_id = tp.tracked_id
         and cp08.eval_date = eval_day.eval_date
         and cp08.eval_slot = '08'
        left join jongga_compare_prices cp09
          on cp09.tracked_id = tp.tracked_id
         and cp09.eval_date = eval_day.eval_date
         and cp09.eval_slot = '09'
        left join naver_ohlcv_1d ohlcv
          on ohlcv.ticker = tp.stock_code
         and ohlcv.trade_date = eval_day.eval_date
        where (%(grade_filter)s = 'ALL' or tp.grade = %(grade_filter)s)
          and (
            %(keyword)s = ''
            or lower(tp.stock_code) like %(keyword_like)s
            or lower(tp.stock_name) like %(keyword_like)s
          )
        order by tp.featured_rank asc, tp.signal_rank asc
        """

        params = {
            'run_date': run_date,
            'grade_filter': normalized_grade,
            'keyword': keyword,
            'keyword_like': keyword_like,
        }
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = [dict(row) for row in cur.fetchall()]

        if not rows:
            meta = self.fetch_run_meta(date_arg)
            run_meta = None
            if meta:
                run_meta = {
                    'run_id': meta['run_id'],
                    'run_date': meta['run_date'],
                    'created_at': meta['created_at'],
                    'runtime_meta': meta.get('runtime_meta'),
                    'total_candidates': meta.get('total_candidates'),
                    'filtered_count': meta.get('filtered_count'),
                }
            empty_summary = _summary_for([], 'roi_09', 'outcome_09')
            return {
                'run_meta': run_meta,
                'summary': empty_summary,
                'summary_08': _summary_for([], 'roi_08', 'outcome_08'),
                'summary_09': empty_summary,
                'comparison': {'better_slot': '-', 'win_rate_08': 0.0, 'win_rate_09': 0.0, 'edge_pct': 0.0},
                'grade_rows': [],
                'page_rows': [],
                'page': 1,
                'total_pages': 0,
            }

        for row in rows:
            row['roi_08'] = _roi(row.get('entry_price'), row.get('eval_08_price'))
            row['roi_09'] = _roi(row.get('entry_price'), row.get('eval_09_price'))
            row['outcome_08'] = _outcome(row.get('roi_08'))
            row['outcome_09'] = _outcome(row.get('roi_09'))
            row['outcome'] = row['outcome_09']
            row['roi'] = row['roi_09']

        filtered_rows = rows
        if normalized_outcome != 'ALL':
            filtered_rows = [row for row in rows if row.get('outcome_09') == normalized_outcome]

        total = len(filtered_rows)
        total_pages = 0 if total == 0 else max(1, (total + safe_page_size - 1) // safe_page_size)
        safe_page = 1 if total_pages == 0 else min(max(requested_page, 1), total_pages)
        start = (safe_page - 1) * safe_page_size
        page_rows = filtered_rows[start : start + safe_page_size]

        summary_08 = _summary_for(filtered_rows, 'roi_08', 'outcome_08')
        summary_09 = _summary_for(filtered_rows, 'roi_09', 'outcome_09')
        edge = round(summary_08['win_rate'] - summary_09['win_rate'], 2)
        if edge > 0:
            better_slot = '08'
        elif edge < 0:
            better_slot = '09'
        else:
            better_slot = '-'

        first = rows[0]
        run_meta = {
            'run_id': first['run_id'],
            'run_date': first['run_date'],
            'created_at': first['created_at'],
            'runtime_meta': first.get('runtime_meta'),
            'total_candidates': first.get('total_candidates'),
            'filtered_count': first.get('filtered_count'),
        }
        return {
            'run_meta': run_meta,
            'summary': summary_09,
            'summary_08': summary_08,
            'summary_09': summary_09,
            'comparison': {
                'better_slot': better_slot,
                'win_rate_08': summary_08['win_rate'],
                'win_rate_09': summary_09['win_rate'],
                'edge_pct': abs(edge),
            },
            'grade_rows': _grade_summary_for(filtered_rows),
            'page_rows': page_rows,
            'page': safe_page,
            'total_pages': total_pages,
        }

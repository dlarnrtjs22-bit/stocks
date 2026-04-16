# API 명세

## GET `/api/health`

- 서버 상태 확인

## GET `/api/closing-bet/dates`

- 조회 가능한 run 날짜 목록 반환

## GET `/api/closing-bet`

### query

- `date`: `latest` 또는 `YYYY-MM-DD`
- `grade`: `ALL`, `S`, `A`, `B`, `C`
- `q`: 종목명/티커 검색어
- `page`
- `page_size`

### response

- 기준 정보
- featured 종목
- 페이지 목록
- grade 분포

## GET `/api/performance`

### query

- `date`
- `grade`
- `outcome`
- `q`
- `page`
- `page_size`

### response

- 요약 지표
- 등급별 요약
- 거래 목록

## GET `/api/batches`

- Data Status 카드 목록
- Run All 상태

## POST `/api/batches/{task_id}/run`

- 개별 배치 실행 시작

## POST `/api/batches/run-all`

- 전체 배치 순차 실행 시작

## GET `/api/batches/{task_id}/preview`

- 미리보기 표 데이터 반환

## GET `/api/batches/{task_id}/logs`

- 저장된 로그 tail 반환
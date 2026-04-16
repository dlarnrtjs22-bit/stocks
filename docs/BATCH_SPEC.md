# 배치 명세

## 원칙

- 배치 실행은 `stocks_new/batch/runtime_source` 내부 코드만 사용한다.
- 런타임에서 기존 프로젝트를 참조하지 않는다.
- 배치 결과는 DB 에 적재하고, 조회 화면은 DB read model 만 사용한다.

## 태스크 목록

- `daily_prices`
- `institutional_trend`
- `ai_analysis`
- `market_context`
- `program_trend`
- `vcp_signals`
- `ai_jongga_v2`

## Run All 순서

1. `daily_prices`
2. `institutional_trend`
3. `ai_analysis`
4. `market_context`
5. `program_trend`
6. `vcp_signals`
7. `ai_jongga_v2`

## 로그 정책

- 각 태스크는 `runtime/logs` 에 stdout/stderr 로그를 남긴다.
- Data Status 화면은 저장된 로그의 tail 만 보여준다.
- 실시간 polling 은 사용하지 않는다.
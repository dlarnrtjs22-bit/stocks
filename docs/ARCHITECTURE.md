# 아키텍처

## 원칙

- 배치와 조회를 분리한다.
- 조회는 read model 과 view 만 사용한다.
- DB 연결은 `psycopg_pool` 로 관리한다.
- 프론트는 React + Vite 정적 빌드 결과를 사용한다.

## 실행 흐름

1. 배치가 원천 데이터를 수집한다.
2. 배치가 분석 결과를 `jongga_runs`, `jongga_signals` 에 저장한다.
3. 조회 API 는 `vw_jongga_signal_read`, `vw_batch_status` 를 조회한다.
4. 프론트는 `/api/*` 만 호출하고, 렌더링은 정적 번들에서 처리한다.

## 성능 방향

- Data Status: 메타 조회만 수행
- 종가배팅: read model 1회 조회
- 누적 성과: read model 기반 집계
- 로그: 눌렀을 때만 읽기
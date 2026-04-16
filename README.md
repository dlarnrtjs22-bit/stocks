# stocks

국내 주식 종가배팅/대시보드 프로젝트입니다.

배치 수집기, 신호 생성기, FastAPI 백엔드, React 프론트엔드로 구성되어 있으며, 종가배팅 후보 선정, 대시보드 조회, 성과 비교, 계좌 연동 수동 새로고침 기능을 포함합니다.

## 주요 기능

- 종가배팅 후보 생성
- 시장/수급/뉴스/장중 압력 기반 점수화
- 추천 후보 조회 화면
- 다음 거래일 08시 NXT / 09시 정규장 비교 성과 화면
- 시장/추천/계좌 상태를 한 번에 보는 대시보드
- 키움 계좌 연동 수동 새로고침

## 기술 스택

- Backend: FastAPI, psycopg, PostgreSQL
- Frontend: React, TypeScript, Vite
- Batch: Python
- Data sources: Naver, Kiwoom

## 디렉터리 구조

```text
backend/   FastAPI API, 조회 서비스, SQL read models
batch/     데이터 수집/신호 생성 배치
frontend/  React + Vite UI
docs/      API/아키텍처/전략 문서
db/        DB 관련 디렉터리
```

## 실행 방법

### 1. Python 패키지 설치

```bash
python -m pip install -e .
```

### 2. 프론트엔드 패키지 설치

```bash
cd frontend
npm install
```

### 3. 환경 변수 설정

루트에 `.env` 파일을 만들고 `.env.example`을 참고해 값을 채웁니다.

민감 정보는 저장소에 포함하지 않도록 설계되어 있습니다.

- 키움 앱키 / 시크릿
- OAuth 토큰
- DB 비밀번호

### 4. 프론트 빌드

```bash
cd frontend
npm run build
```

### 5. 백엔드 실행

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 5056
```

접속:

- App: `http://127.0.0.1:5056`
- Health: `http://127.0.0.1:5056/api/health`

## 개발 모드

프론트 개발 서버:

```bash
cd frontend
npm run dev
```

개발 모드에서 `/api` 요청은 백엔드 `127.0.0.1:5056`으로 프록시됩니다.

## 환경 변수

예시는 `.env.example`을 참고하세요.

대표 항목:

- `APP_HOST`
- `APP_PORT`
- `FRONTEND_PORT`
- `DATABASE_URL` 또는 `SUPABASE_*`
- `STORAGE_BACKEND`

## 문서

- [API 명세](docs/API_SPEC.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [배치 명세](docs/BATCH_SPEC.md)
- [종가배팅 매매원칙](docs/CLOSING_BET_PRINCIPLES.md)

## 보안 주의

아래는 `.gitignore`로 제외됩니다.

- 로컬 `.env`
- 앱키 / 시크릿 파일
- OAuth 토큰 JSON
- 수집 데이터
- 런타임 로그
- 캐시 / 빌드 산출물

공개 저장소에 실제 운영 키와 비밀번호를 커밋하지 마세요.

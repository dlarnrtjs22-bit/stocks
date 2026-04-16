from __future__ import annotations

# 이 파일은 헬스 체크 라우트를 정의한다.
from fastapi import APIRouter

router = APIRouter(prefix='/api', tags=['health'])


# 이 엔드포인트는 서버와 DB 풀이 정상적으로 떠 있는지 확인할 때 사용한다.
@router.get('/health')
def health_check() -> dict[str, str]:
    return {'status': 'ok'}


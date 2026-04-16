from __future__ import annotations

# 이 파일은 앱 전체에서 공통으로 사용할 로깅 설정을 담당한다.
import logging


# 이 함수는 중복 설정 없이 콘솔 로깅을 초기화한다.
def configure_logging() -> None:
    if logging.getLogger().handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    )


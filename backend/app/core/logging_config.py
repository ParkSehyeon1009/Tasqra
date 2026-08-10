# =============================================================================
# 이 파일의 책임: 파이썬 표준 logging을 설정해서, 모든 로그 라인에 middleware.py가
#   contextvars에 저장한 request_id가 자동으로 찍히게 만든다.
# 다른 파일과의 관계: middleware.py의 request_id_ctx_var를 읽어오는 로깅 Filter를
#   정의하고, main.py의 앱 시작 시점(또는 모듈 import 시점)에 setup_logging()을 호출한다.
# Spring 비교: logback.xml에서 %X{traceId} 패턴 + MDC를 쓰는 것과 동일한 목적.
#   Spring은 설정 파일(XML/yml)로 선언하지만, 여기서는 logging.Filter 서브클래스를
#   코드로 작성해서 LogRecord에 request_id 속성을 주입하는 방식입니다.
# =============================================================================

import logging

from app.core.middleware import request_id_ctx_var


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx_var.get()
        return True


#   - main.py에서 앱 생성 전에 이 함수를 한 번 호출해서 등록합니다.
def setup_logging() -> None:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [request_id=%(request_id)s] %(name)s - %(message)s"
        )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdLogFilter())

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level=logging.INFO)

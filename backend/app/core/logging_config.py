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
#   - worker.py도 모듈 수준에서 호출합니다. 워커 프로세스는 main.py를 거치지
#     않아서(celery -A app.worker.celery_app), 거기서 부르지 않으면 워커 로그에
#     [request_id=...]가 아예 붙지 않습니다.

# 핸들러에 이름을 붙여 두고 같은 이름이 이미 있으면 다시 붙이지 않는다.
_HANDLER_NAME = "tasqra-request-id"


def setup_logging() -> None:
    """루트 로거에 request_id를 찍는 핸들러를 붙인다. **두 번 불러도 안전하다.**

    두 번 불리는 것은 가정이 아니라 실제다. main.py가 8행에서 라우터들을 import
    하고 그 사슬이 document_router -> app.worker 로 이어지는데, worker.py가 모듈
    수준에서 이 함수를 부른다. 그래서 API 프로세스에서도 두 번 불린다.

    막지 않으면 루트 로거에 StreamHandler가 두 개 붙어 **모든 로그가 두 줄로**
    나온다. 에러가 아니라서 알아채기 어렵고, 로그를 세는 눈을 망친다.

    Spring 비교: logback은 설정 파일을 한 번만 읽으므로 이 문제가 없다. 코드로
    핸들러를 붙이는 방식이라 멱등성을 직접 챙겨야 한다.
    """
    root_logger = logging.getLogger()
    for existing in root_logger.handlers:
        if existing.name == _HANDLER_NAME:
            return

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [request_id=%(request_id)s] %(name)s - %(message)s"
        )
    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdLogFilter())

    root_logger.addHandler(handler)
    root_logger.setLevel(level=logging.INFO)

# =============================================================================
# 이 파일의 책임: 요청마다 고유한 request_id를 생성해 (1) contextvars에 저장,
#   (2) request.state에 저장, (3) 응답 헤더(X-Request-ID)에 실어 보낸다.
# 다른 파일과의 관계: logging_config.py의 로거 필터가 이 contextvars 값을 읽어
#   모든 로그 라인에 자동으로 request_id를 찍는다. exceptions.py의 핸들러들도
#   request.state.request_id를 읽어 ErrorResponse에 포함시킨다.
# Spring 비교: Spring의 MDC(Mapped Diagnostic Context) + OncePerRequestFilter로
#   요청마다 traceId를 넣고 로그 패턴(%X{traceId})에 자동 출력하는 것과 동일한 구조.
#   contextvars가 MDC의 ThreadLocal 역할을 하는데, 차이는 FastAPI가 비동기이므로
#   ThreadLocal이 아니라 asyncio 태스크 단위로 격리되는 contextvars를 쓴다는 점.
# =============================================================================

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        token = request_id_ctx_var.set(request_id)
        try:
            request.state.request_id = request_id
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx_var.reset(token)

# =============================================================================
# 이 파일의 책임: 요청마다 request_id를 정해 (1) contextvars에 저장, (2) request.state에
#   저장, (3) 응답 헤더(X-Request-ID)에 실어 보내고, (4) 요청 1건당 로그 한 줄을 남긴다.
# 다른 파일과의 관계: logging_config.py의 로거 필터가 이 contextvars 값을 읽어
#   모든 로그 라인에 자동으로 request_id를 찍는다. exceptions.py의 핸들러들도
#   request.state.request_id를 읽어 ErrorResponse에 포함시킨다.
# Spring 비교: Spring의 MDC(Mapped Diagnostic Context) + OncePerRequestFilter로
#   요청마다 traceId를 넣고 로그 패턴(%X{traceId})에 자동 출력하는 것과 동일한 구조.
#   contextvars가 MDC의 ThreadLocal 역할을 하는데, 차이는 FastAPI가 비동기이므로
#   ThreadLocal이 아니라 asyncio 태스크 단위로 격리되는 contextvars를 쓴다는 점.
#   요청 1건당 로그 한 줄은 Spring Boot의 CommonsRequestLoggingFilter에 해당한다.
#
# ⚠ 요청 로그를 왜 따로 남기는가 (SYS-003-1)
#   완료 판정이 "주요 오류가 동일한 응답 형식과 서버 로그에 남고 **요청 단위 추적이
#   가능하다**" 다. 오류 핸들러만 로그를 남기면 오류가 난 요청만 흔적이 있다.
#   그러면 "느렸다" · "404가 났다" · "요청이 서버에 닿았는가" 를 되짚을 수 없다.
#   uvicorn 자체 접근 로그로는 대신할 수 없다 — 그쪽은 별도 로거라 우리 필터가
#   붙지 않아 request_id가 찍히지 않는다.
#
# ⚠ 들어온 X-Request-ID를 이어받는다
#   화면이 오류를 보여줄 때 request_id를 함께 내놓는데(api/http.js), 그 값이 서버가
#   만든 것뿐이면 **화면에서 시작한 흐름을 서버 로그에서 되짚을 수 없다.** 그래서
#   요청에 X-Request-ID가 있으면 그것을 쓴다.
#   다만 **그대로 믿지 않는다.** 외부 입력이 로그에 그대로 들어가면 줄바꿈을 넣어
#   로그를 위조할 수 있다(log injection). 허용 문자와 길이를 제한하고 어긋나면
#   새로 만든다.
# =============================================================================

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="-")

# 요청 단위 로그만 따로 켜고 끌 수 있게 전용 로거를 쓴다.
logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
# 로그와 헤더에 그대로 들어가므로 줄바꿈·공백·제어문자를 허용하지 않는다.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")


def resolve_request_id(incoming: str | None) -> str:
    """이어받을 수 있으면 그 값을, 아니면 새로 만든 값을 돌려준다."""
    if incoming and _SAFE_REQUEST_ID.match(incoming):
        return incoming
    return str(uuid.uuid4())


# --- 요청 밖으로 request_id 를 꺼내는 세 가지 방법 ---------------------------
#
# 워커(Celery)는 미들웨어를 거치지 않는다. 그래서 태스크를 큐에 넣을 때 값을 실어
# 보내고, 워커가 받아서 자기 프로세스의 contextvar 에 심어야 로그에 찍힌다.
# 아래 셋이 그 양쪽 끝이다.


def get_request_id(request: Request) -> str:
    """FastAPI 의존성. 엔드포인트에서 `request_id: str = Depends(get_request_id)`.

    `request.state` 에서 읽는다 — 미들웨어가 거기에 **직접** 심으므로 contextvar
    전달 여부와 무관하게 값이 맞는다. 새 엔드포인트에서는 이쪽을 쓴다.

    Spring 비교: `@RequestAttribute("requestId") String requestId` 로 받는 자리다.
    """
    return getattr(request.state, "request_id", "-")


def current_request_id() -> str:
    """contextvar 에서 읽는다. **엔드포인트 서명을 바꿀 수 없을 때만** 쓴다.

    의존성을 더하려면 함수 서명을 고쳐야 하는데, 남이 만지고 있는 파일에서는
    그것이 충돌 지점이 된다. 그럴 때 한 줄로 끝내려고 둔다.

    요청 밖(워커·스크립트)에서 부르면 `"-"` 다. 값을 못 얻어도 아무것도 깨지지
    않는다 — 추적이 안 될 뿐이다.

    Spring 비교: `MDC.get("requestId")` 를 직접 읽는 것과 같다.
    """
    return request_id_ctx_var.get()


def bind_request_id(request_id: str | None) -> None:
    """받은 값을 이 프로세스의 contextvar 에 심는다. **워커가 부른다.**

    미들웨어가 없는 프로세스에서 미들웨어 역할을 대신하는 자리다. 이것을 부르지
    않으면 태스크 인자로 값을 받아도 로그 필터가 읽을 곳이 없다.

    받은 값을 그대로 믿지 않고 다시 검사한다. 큐 메시지도 결국 외부에서 온 값이
    닿을 수 있는 경로이고, 줄바꿈이 섞이면 로그를 위조할 수 있다(log injection).
    미들웨어가 들어오는 헤더를 검사하는 것과 같은 이유다.
    """
    if request_id and _SAFE_REQUEST_ID.match(request_id):
        request_id_ctx_var.set(request_id)
    else:
        request_id_ctx_var.set("-")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = request_id_ctx_var.set(request_id)
        started = time.perf_counter()
        try:
            request.state.request_id = request_id
            try:
                response = await call_next(request)
            except Exception:
                # 미처리 예외도 요청 줄을 남긴다. 예외 자체는 전역 핸들러가
                # 기록하지만, 어느 요청이었는지는 여기서만 알 수 있다.
                self._log(request, 500, started)
                raise
            response.headers[REQUEST_ID_HEADER] = request_id
            self._log(request, response.status_code, started)
            return response
        finally:
            request_id_ctx_var.reset(token)

    @staticmethod
    def _log(request: Request, status_code: int, started: float) -> None:
        # 쿼리 문자열은 남기지 않는다. 검색어처럼 사용자가 넣은 값이 로그에
        # 쌓이면 지우기 어렵다. 경로만으로 어느 엔드포인트인지 알 수 있다.
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            status_code,
            (time.perf_counter() - started) * 1000,
        )

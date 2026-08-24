# =============================================================================
# 이 파일의 책임: 오류 응답 형식(SYS-003-1)이 **한 가지**인지 검증한다.
#   특히 프레임워크가 내는 오류(없는 경로 404 · 허용되지 않은 메서드 405)가
#   우리 형식으로 나오는지 본다.
#
#   왜 이 검사가 필요한가 — 실제로 놓쳤다
#     산출물 다운로드 주소를 잘못 만들어 호출했더니 `{"detail":"Not Found"}` 가
#     왔다. `code` 도 `request_id` 도 없어서 로그와 이어붙일 수 없었다.
#     우리가 HTTPException 을 던지지 않아도 **라우터가 던진다.**
#
# 다른 파일과의 관계: core/exceptions.py · core/error_codes.py · main.py
#
# ⚠ 서버를 띄우지 않는다
#   핸들러는 async 함수라서 asyncio.run 으로 직접 부른다. TestClient 를 쓰면 DB
#   연결과 설정이 필요해 이 검사의 범위를 넘는다.
#
# Spring 비교: @RestControllerAdvice 가 NoHandlerFoundException 까지 잡는지
#   확인하는 것과 같다. Spring 도 그것을 따로 켜야 잡힌다.
# =============================================================================

import asyncio
import json
from types import SimpleNamespace

from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    business_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.middleware import REQUEST_ID_HEADER


def _request(request_id="req-1234abcd", method="GET", path="/api/projects/1/nope"):
    """핸들러가 실제로 읽는 것만 담은 최소 요청."""
    return SimpleNamespace(
        state=SimpleNamespace(request_id=request_id),
        method=method,
        url=SimpleNamespace(path=path),
    )


def _body(response):
    return json.loads(bytes(response.body).decode("utf-8"))


# --- 없는 경로 · 허용되지 않은 메서드 ----------------------------------------


def test_unknown_path_uses_our_format():
    """FastAPI 기본 형식({"detail": ...})이 나가면 안 된다."""
    response = asyncio.run(
        http_exception_handler(_request(), StarletteHTTPException(status_code=404))
    )
    body = _body(response)

    assert response.status_code == 404
    assert body["code"] == ErrorCode.ROUTE_NOT_FOUND.code
    assert body["request_id"] == "req-1234abcd"
    assert "detail" not in body
    assert response.headers[REQUEST_ID_HEADER] == "req-1234abcd"


def test_method_not_allowed_keeps_status_and_allow_header():
    """405 를 404 로 바꾸면 경로가 없는 것과 방식이 틀린 것을 구별할 수 없다."""
    exception = StarletteHTTPException(status_code=405, headers={"Allow": "GET, POST"})
    response = asyncio.run(http_exception_handler(_request(method="DELETE"), exception))

    assert response.status_code == 405
    assert _body(response)["code"] == ErrorCode.METHOD_NOT_ALLOWED.code
    # Starlette 이 붙여 주는 Allow 를 우리가 지우면 규약을 깨는 것이다.
    assert response.headers["allow"] == "GET, POST"
    assert response.headers[REQUEST_ID_HEADER] == "req-1234abcd"


def test_unknown_status_passes_detail_through():
    """모르는 상태코드는 메시지를 지어내지 않고 detail 을 옮긴다."""
    exception = StarletteHTTPException(status_code=418, detail="주전자입니다")
    response = asyncio.run(http_exception_handler(_request(), exception))
    body = _body(response)

    assert response.status_code == 418
    assert body["code"] == "HTTP_ERROR"
    assert body["message"] == "주전자입니다"


# --- 형식이 하나인지 -----------------------------------------------------------


def test_every_handler_returns_the_same_keys():
    """화면이 한 가지 형식만 처리하면 되도록 열쇠가 같아야 한다."""
    responses = [
        asyncio.run(
            business_error_handler(_request(), BusinessError(ErrorCode.PROJECT_NOT_FOUND))
        ),
        asyncio.run(
            http_exception_handler(_request(), StarletteHTTPException(status_code=404))
        ),
        asyncio.run(unhandled_exception_handler(_request(), RuntimeError("boom"))),
    ]
    for response in responses:
        body = _body(response)
        assert set(body) == {"code", "message", "request_id"}, body
        assert body["request_id"] == "req-1234abcd"
        assert response.headers[REQUEST_ID_HEADER] == "req-1234abcd"


def test_request_id_falls_back_when_middleware_did_not_run():
    """미들웨어 이전에 예외가 나도 핸들러가 터지지 않아야 한다."""
    request = SimpleNamespace(
        state=SimpleNamespace(), method="GET", url=SimpleNamespace(path="/x")
    )
    response = asyncio.run(
        http_exception_handler(request, StarletteHTTPException(status_code=404))
    )
    assert _body(response)["request_id"] == "-"

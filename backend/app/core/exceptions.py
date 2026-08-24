# =============================================================================
# 이 파일의 책임: (1) 비즈니스 예외의 기본 클래스(BusinessError)를 정의하고,
#   (2) 그 예외를 포함해 검증 실패, 미처리 예외까지 일관된 JSON(ErrorResponse)
#   형태로 응답하는 전역 예외 핸들러 3종을 제공한다.
# 다른 파일과의 관계: error_codes.py의 ErrorCode를 받아 BusinessError를 만들고,
#   schemas/error.py의 ErrorResponse로 직렬화하며, middleware.py가 저장한
#   request_id를 응답에 실어 보낸다. main.py에서 app.add_exception_handler로 등록한다.
# Spring 비교: BusinessError = 커스텀 BusinessException,
#   아래 handler 3종 = @RestControllerAdvice + @ExceptionHandler 메서드들.
#   Spring은 어노테이션으로 전역 등록되지만, FastAPI는 main.py에서
#   명시적으로 app.add_exception_handler(...)를 호출해 등록해야 합니다.
# =============================================================================

from logging import getLogger
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.error_codes import ErrorCode
from app.core.middleware import REQUEST_ID_HEADER
from app.schemas.error import ErrorResponse, ValidationErrorResponse, FieldError


def _request_id(request: Request) -> str:
    """request_id를 안전하게 꺼낸다.

    RequestIdMiddleware 가 지나가기 전에 예외가 나면 `request.state.request_id`
    자체가 없다. 그때 AttributeError 가 나면 **오류 핸들러가 오류를 내면서
    응답 본문이 사라진다** — 원인 파악이 가장 필요한 순간에 가장 알 수 없게 된다.
    그래서 없으면 로거 기본값과 같은 "-" 를 쓴다.
    """
    return getattr(request.state, "request_id", "-")


class BusinessError(Exception):
    # detail: 사용자에게 보여줄 추가 정보 (예: "최대 10MB까지 업로드 가능합니다").
    #   생략하면(None) error_code.message가 그대로 응답 메시지로 쓰인다.
    #   (예: BusinessError(ErrorCode.FILE_TOO_LARGE, detail=f"업로드 크기={size}MB"))
    def __init__(self, error_code: ErrorCode, detail: str | None = None) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail or error_code.message)


logger = getLogger(__name__)

async def business_error_handler(request: Request, exc: BusinessError) -> JSONResponse:
    logger.warning(
        "Business error: method=%s path=%s code=%s status=%s",
        request.method,
        request.url.path,
        exc.error_code.code,
        exc.error_code.status_code,
    )
    request_id = _request_id(request)
    body = ErrorResponse(
        code= exc.error_code.code,
        message= exc.detail or exc.error_code.message,
        request_id= request_id
    )
    # 오류 응답에도 헤더를 실어 준다. 본문을 읽지 못하는 경우(파일 다운로드 등)에도
    # 사용자가 request_id 를 전달할 수 있어야 한다.
    return JSONResponse(
        status_code=exc.error_code.status_code,
        content=body.model_dump(),
        headers={REQUEST_ID_HEADER: request_id},
    )
    

# FastAPI/Pydantic의 요청 검증 실패(RequestValidationError) 전용 핸들러
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    
    field_errors = [
        FieldError(field=".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][-1]), reason=err["msg"])
        for err in exc.errors()
    ]

    logger.warning(
        "Validation failed: path=%s errors=%s",
        request.url.path,
        [e.field for e in field_errors]
    )

    request_id = _request_id(request)
    body = ValidationErrorResponse(
        code="VALIDATION_ERROR",
        message="요청 데이터 검증에 실패했습니다",
        request_id=request_id,
        errors=field_errors
    )
    return JSONResponse(
        status_code=422,
        content=body.model_dump(),
        headers={REQUEST_ID_HEADER: request_id},
    )


# 그 외 예상하지 못한 모든 예외(Exception)를 잡는 최후의 보루 핸들러
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    # 경로를 함께 남긴다. 미처리 예외는 traceback 만으로는 어느 요청이었는지
    # 바로 보이지 않는 경우가 있다.
    logger.exception(
        "Unhandled exception occurred: method=%s path=%s",
        request.method,
        request.url.path,
    )
    body = ErrorResponse(
        code= ErrorCode.INTERNAL_ERROR.code,
        message= ErrorCode.INTERNAL_ERROR.message,
        request_id= request_id
    )
    # ⚠️ 이 핸들러의 응답은 RequestIdMiddleware 바깥에서 만들어진다(Starlette 의
    #   ServerErrorMiddleware 가 가장 바깥이다). 그래서 미들웨어가 헤더를 붙여 줄
    #   수 없고, 여기서 직접 넣어야 500 응답에도 X-Request-ID 가 실린다.
    return JSONResponse(
        status_code=ErrorCode.INTERNAL_ERROR.status_code,
        content=body.model_dump(),
        headers={REQUEST_ID_HEADER: request_id},
        )

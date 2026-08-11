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
from app.schemas.error import ErrorResponse, ValidationErrorResponse, FieldError


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
    body = ErrorResponse(
        code= exc.error_code.code,
        message= exc.detail or exc.error_code.message,
        request_id= request.state.request_id
    )
    return JSONResponse(status_code=exc.error_code.status_code, content=body.model_dump())
    

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

    body = ValidationErrorResponse(
        code="VALIDATION_ERROR",
        message="요청 데이터 검증에 실패했습니다",
        request_id=request.state.request_id,
        errors=field_errors
    )
    return JSONResponse(status_code=422, content=body.model_dump())


# 그 외 예상하지 못한 모든 예외(Exception)를 잡는 최후의 보루 핸들러
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception occurred")
    body = ErrorResponse(
        code= ErrorCode.INTERNAL_ERROR.code,
        message= ErrorCode.INTERNAL_ERROR.message,
        request_id= request.state.request_id
    )
    return JSONResponse(
        status_code=ErrorCode.INTERNAL_ERROR.status_code, 
        content=body.model_dump()
        )

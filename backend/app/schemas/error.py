# =============================================================================
# 이 파일의 책임: 에러 응답의 JSON 스키마(Pydantic BaseModel)를 정의한다.
#   core/exceptions.py의 핸들러들이 이 모델을 사용해 응답 바디를 직렬화한다.
# 다른 파일과의 관계: core/error_codes.py(ErrorCode) + core/exceptions.py(핸들러)와
#   묶여서 하나의 "에러 처리 파이프라인"을 구성한다. 이 파일은 그중 "출력 형태"만 담당.
# Spring 비교: @RestControllerAdvice에서 반환하는 ErrorResponse DTO와 동일.
#   Spring도 보통 code/message/timestamp 같은 필드를 가진 공통 에러 응답 DTO를
#   두고, 검증 에러일 때만 필드별 에러 리스트를 추가로 얹는 서브클래스/확장을 씁니다.
# =============================================================================

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str

class FieldError(BaseModel):
    field: str
    reason: str

class ValidationErrorResponse(ErrorResponse):
    errors: list[FieldError]

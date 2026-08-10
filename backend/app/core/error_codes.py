# =============================================================================
# 이 파일의 책임: 서비스 전체에서 사용할 "에러의 종류"를 한 곳에 모아 정의한다.
#   각 케이스는 (내부 식별 코드, 사용자 노출 메시지, HTTP 상태 코드) 3요소를 가진다.
# 다른 파일과의 관계: exceptions.py의 BusinessError가 이 Enum 멤버를 받아서
#   예외를 표현하고, 전역 exception_handler가 이 정보를 ErrorResponse로 변환한다.
# Spring 비교: 커스텀 ErrorCode enum + BusinessException(errorCode) 조합과 동일.
#   Spring에서 흔히 ErrorCode 인터페이스/enum에 (code, message, HttpStatus)를
#   같이 묶어두는 패턴을 그대로 Python Enum으로 옮긴 것입니다.
# =============================================================================

from enum import Enum


class ErrorCode(Enum):

    USER_NOT_FOUND = ("USER_NOT_FOUND", "사용자를 찾을 수 없습니다", 404)
    DUPLICATE_USER = ("DUPLICATE_USER", "이미 존재하는 사용자입니다", 409)
    INTERNAL_ERROR = ("INTERNAL_ERROR", "서버 내부 오류가 발생했습니다", 500)

    # --- PDF Brief AI 도메인 에러코드 ---------------------------------------
    INVALID_FILE_TYPE = ("INVALID_FILE_TYPE", "지원하지 않는 파일 형식입니다.", 400)
    FILE_TOO_LARGE = ("FILE_TOO_LARGE", "파일 크기가 허용 범위를 초과했습니다.", 413)
    TOO_MANY_PAGES = ("TOO_MANY_PAGES", "페이지 수가 허용 범위를 초과했습니다.", 413)
    CONTENT_TOO_LARGE = ("CONTENT_TOO_LARGE", "추출된 문서 내용이 허용 범위를 초과했습니다.", 413)
    EXTRACTION_FAILED = ("EXTRACTION_FAILED", "문서에서 텍스트를 추출할 수 없습니다.", 422)
    DOCUMENT_NOT_FOUND = ("DOCUMENT_NOT_FOUND", "문서를 찾을 수 없습니다.", 404)
    NOT_EXTRACTED_YET = ("NOT_EXTRACTED_YET", "텍스트 추출이 완료되지 않았습니다.", 409)
    ANALYZER_NOT_FOUND = ("ANALYZER_NOT_FOUND", "지원하지 않는 분석기입니다.", 400)
    AI_PROVIDER_ERROR = ("AI_PROVIDER_ERROR", "AI 분석 중 오류가 발생했습니다.", 502)
    AI_TIMEOUT = ("AI_TIMEOUT", "AI 응답 시간이 초과되었습니다.", 504)

    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code

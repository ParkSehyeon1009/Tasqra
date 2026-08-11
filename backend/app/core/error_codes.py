from enum import Enum


class ErrorCode(Enum):
    USER_NOT_FOUND = ("USER_NOT_FOUND", "사용자를 찾을 수 없습니다.", 404)
    DUPLICATE_USER = ("DUPLICATE_USER", "이미 가입된 이메일입니다.", 409)
    DUPLICATE_LOGIN_ID = ("DUPLICATE_LOGIN_ID", "이미 사용 중인 아이디입니다.", 409)
    INVALID_CREDENTIALS = ("INVALID_CREDENTIALS", "이메일 또는 비밀번호가 올바르지 않습니다.", 401)
    UNAUTHORIZED = ("UNAUTHORIZED", "로그인이 필요합니다.", 401)
    INVALID_REFRESH_TOKEN = ("INVALID_REFRESH_TOKEN", "유효하지 않거나 만료된 로그인 세션입니다.", 401)
    PROJECT_NOT_FOUND = ("PROJECT_NOT_FOUND", "프로젝트를 찾을 수 없습니다.", 404)
    PROJECT_FORBIDDEN = ("PROJECT_FORBIDDEN", "프로젝트에 접근할 권한이 없습니다.", 403)
    DUPLICATE_MEMBER = ("DUPLICATE_MEMBER", "이미 프로젝트에 참여 중인 사용자입니다.", 409)
    MEMBER_NOT_FOUND = ("MEMBER_NOT_FOUND", "프로젝트 멤버를 찾을 수 없습니다.", 404)
    OWNER_ROLE_RESERVED = ("OWNER_ROLE_RESERVED", "프로젝트 소유자 역할은 이 작업으로 변경할 수 없습니다.", 409)
    INVALID_PROJECT_DATES = ("INVALID_PROJECT_DATES", "프로젝트 시작일은 종료일보다 늦을 수 없습니다.", 400)
    INVALID_PROJECT_NAME = ("INVALID_PROJECT_NAME", "프로젝트 이름은 비워둘 수 없습니다.", 400)
    INVITATION_NOT_FOUND = ("INVITATION_NOT_FOUND", "프로젝트 초대를 찾을 수 없습니다.", 404)
    INVITATION_NOT_PENDING = ("INVITATION_NOT_PENDING", "이미 처리된 프로젝트 초대입니다.", 409)
    INVALID_FILE_TYPE = ("INVALID_FILE_TYPE", "지원하지 않는 파일 형식입니다.", 400)
    INVALID_EXTRACTION_STRATEGY = ("INVALID_EXTRACTION_STRATEGY", "이 파일에서 사용할 수 없는 텍스트 추출 방식입니다.", 400)
    OCR_EDIT_CONFLICT = ("OCR_EDIT_CONFLICT", "다른 사용자가 먼저 수정했습니다. 최신 내용을 다시 불러와 주세요.", 409)
    FILE_TOO_LARGE = ("FILE_TOO_LARGE", "파일 크기가 허용 범위를 초과했습니다.", 413)
    TOO_MANY_PAGES = ("TOO_MANY_PAGES", "페이지 수가 허용 범위를 초과했습니다.", 413)
    CONTENT_TOO_LARGE = ("CONTENT_TOO_LARGE", "추출된 문서 내용이 허용 범위를 초과했습니다.", 413)
    EXTRACTION_FAILED = ("EXTRACTION_FAILED", "문서에서 텍스트를 추출할 수 없습니다.", 422)
    DOCUMENT_NOT_FOUND = ("DOCUMENT_NOT_FOUND", "문서를 찾을 수 없습니다.", 404)
    NOT_EXTRACTED_YET = ("NOT_EXTRACTED_YET", "텍스트 추출이 완료되지 않았습니다.", 409)
    ANALYZER_NOT_FOUND = ("ANALYZER_NOT_FOUND", "지원하지 않는 분석기입니다.", 400)
    AI_PROVIDER_ERROR = ("AI_PROVIDER_ERROR", "AI 분석 중 오류가 발생했습니다.", 502)
    AI_TIMEOUT = ("AI_TIMEOUT", "AI 응답 시간이 초과되었습니다.", 504)
    INTERNAL_ERROR = ("INTERNAL_ERROR", "서버 내부 오류가 발생했습니다.", 500)

    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code

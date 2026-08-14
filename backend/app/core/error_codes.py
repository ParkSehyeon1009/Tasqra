# =============================================================================
# 이 파일의 책임: 서비스 전체에서 쓰는 "에러의 종류"를 한 곳에 모아 정의한다.
#   각 항목은 (내부 식별 코드, 사용자 노출 메시지, HTTP 상태 코드) 3요소를 가진다.
# 다른 파일과의 관계: exceptions.py 의 BusinessError 가 이 Enum 멤버를 받아
#   예외를 표현하고, 전역 예외 핸들러가 schemas/error.py 의 ErrorResponse 로
#   바꿔 응답한다. 응답 본문의 필드 이름은 code 다(error_code 가 아니다).
# Spring 비교: ErrorCode enum + BusinessException(errorCode) 조합과 같다.
#   Spring 에서 ErrorCode enum 에 (code, message, HttpStatus) 를 묶어두는
#   패턴을 그대로 Python Enum 으로 옮긴 것이다.
#
# 코드를 추가할 때의 기준 — 프런트가 다르게 처리해야 하는가.
#   화면이 똑같이 "오류가 났습니다" 만 띄울 거라면 코드를 나누지 않는다.
#   요청 형식 오류는 Pydantic 이 422 VALIDATION_ERROR 로 먼저 막으므로
#   별도 코드를 두지 않는다.
# =============================================================================

from enum import Enum


class ErrorCode(Enum):
    DOCUMENT_RETRY_NOT_ALLOWED = ("DOCUMENT_RETRY_NOT_ALLOWED", "실패한 문서만 다시 처리할 수 있습니다.", 409)
    PROCESS_QUEUE_UNAVAILABLE = ("PROCESS_QUEUE_UNAVAILABLE", "문서 처리 작업을 등록하지 못했습니다. 잠시 후 다시 시도해 주세요.", 503)
    DUPLICATE_DOCUMENT = ("DUPLICATE_DOCUMENT", "프로젝트에 동일한 문서가 이미 등록되어 있습니다.", 409)
    INVALID_DOCUMENT_TYPE = ("INVALID_DOCUMENT_TYPE", "지원하지 않는 문서 유형입니다.", 400)
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
    DUPLICATE_INVITATION = ("DUPLICATE_INVITATION", "이미 대기 중인 프로젝트 초대가 있습니다.", 409)
    INVALID_FILE_TYPE = ("INVALID_FILE_TYPE", "지원하지 않는 파일 형식입니다.", 400)
    INVALID_EXTRACTION_STRATEGY = ("INVALID_EXTRACTION_STRATEGY", "이 파일에서 사용할 수 없는 텍스트 추출 방식입니다.", 400)
    OCR_EDIT_CONFLICT = ("OCR_EDIT_CONFLICT", "다른 사용자가 먼저 수정했습니다. 최신 내용을 다시 불러와 주세요.", 409)
    OCR_CONTENT_MAPPING_CONFLICT = ("OCR_CONTENT_MAPPING_CONFLICT", "OCR 영역과 문서 본문의 연결 정보가 일치하지 않습니다. 문서를 다시 추출해 주세요.", 409)
    OCR_INVALID_STRUCTURE = ("OCR_INVALID_STRUCTURE", "OCR 요소 종류와 단락 경계 설정이 올바르지 않습니다.", 400)
    FILE_TOO_LARGE = ("FILE_TOO_LARGE", "파일 크기가 허용 범위를 초과했습니다.", 413)
    TOO_MANY_PAGES = ("TOO_MANY_PAGES", "페이지 수가 허용 범위를 초과했습니다.", 413)
    CONTENT_TOO_LARGE = ("CONTENT_TOO_LARGE", "추출된 문서 내용이 허용 범위를 초과했습니다.", 413)
    EXTRACTION_FAILED = ("EXTRACTION_FAILED", "문서에서 텍스트를 추출할 수 없습니다.", 422)
    DOCUMENT_NOT_FOUND = ("DOCUMENT_NOT_FOUND", "문서를 찾을 수 없습니다.", 404)
    NOT_EXTRACTED_YET = ("NOT_EXTRACTED_YET", "텍스트 추출이 완료되지 않았습니다.", 409)
    ANALYZER_NOT_FOUND = ("ANALYZER_NOT_FOUND", "지원하지 않는 분석기입니다.", 400)
    AI_PROVIDER_ERROR = ("AI_PROVIDER_ERROR", "AI 분석 중 오류가 발생했습니다.", 502)
    AI_TIMEOUT = ("AI_TIMEOUT", "AI 응답 시간이 초과되었습니다.", 504)
    # ── OCR 검수 (리비전 0004: document_pages · ocr_groups · ocr_elements) ──
    PAGE_NOT_FOUND = ("PAGE_NOT_FOUND", "문서 페이지를 찾을 수 없습니다.", 404)
    OCR_ELEMENT_NOT_FOUND = ("OCR_ELEMENT_NOT_FOUND", "인식 영역을 찾을 수 없습니다.", 404)
    OCR_ELEMENT_DELETED = ("OCR_ELEMENT_DELETED", "삭제된 인식 영역은 수정할 수 없습니다.", 409)
    INVALID_BBOX = ("INVALID_BBOX", "인식 영역의 좌표가 올바르지 않습니다.", 400)
    RE_OCR_FAILED = ("RE_OCR_FAILED", "선택한 영역을 다시 인식하지 못했습니다.", 502)
    REVIEW_NOT_COMPLETED = ("REVIEW_NOT_COMPLETED", "검수가 완료되지 않았습니다.", 409)
    REVIEW_ALREADY_COMPLETED = ("REVIEW_ALREADY_COMPLETED", "이미 검수가 완료된 문서입니다.", 409)

    # ── AI 제안 승인 공통 (amount_items · decisions · schedule_items) ──
    SUGGESTION_ALREADY_DECIDED = ("SUGGESTION_ALREADY_DECIDED", "이미 승인 또는 거부된 제안입니다.", 409)
    STALE_SUGGESTION = ("STALE_SUGGESTION", "문서가 수정되어 오래된 제안입니다. 다시 분석해 주세요.", 409)

    # ── 금액 (amount_items) ──
    AMOUNT_ITEM_NOT_FOUND = ("AMOUNT_ITEM_NOT_FOUND", "금액 항목을 찾을 수 없습니다.", 404)
    AMOUNT_NOT_ANALYZED = ("AMOUNT_NOT_ANALYZED", "금액 분석이 완료되지 않았습니다.", 409)
    CURRENCY_MISMATCH = ("CURRENCY_MISMATCH", "통화가 다른 금액은 함께 집계할 수 없습니다.", 409)
    NO_APPROVED_AMOUNTS = ("NO_APPROVED_AMOUNTS", "집계할 승인된 금액이 없습니다.", 409)

    # ── 결정사항 · 일정 (decisions · schedule_items) ──
    DECISION_NOT_FOUND = ("DECISION_NOT_FOUND", "결정사항을 찾을 수 없습니다.", 404)
    SCHEDULE_ITEM_NOT_FOUND = ("SCHEDULE_ITEM_NOT_FOUND", "일정을 찾을 수 없습니다.", 404)

    # ── 산출물 (deliverables) ──
    DELIVERABLE_NOT_FOUND = ("DELIVERABLE_NOT_FOUND", "산출물을 찾을 수 없습니다.", 404)
    FORMAT_REQUIRED = ("FORMAT_REQUIRED", "파일 형식을 선택해 주세요.", 422)
    PERIOD_REQUIRED = ("PERIOD_REQUIRED", "대상 기간을 선택해 주세요.", 422)
    DELIVERABLE_EMPTY = ("DELIVERABLE_EMPTY", "선택한 기간에 담을 내용이 없습니다.", 422)
    DELIVERABLE_GENERATION_FAILED = ("DELIVERABLE_GENERATION_FAILED", "산출물 파일을 만들지 못했습니다.", 500)

    # ── AI 모델 (금액 모델을 따로 돌리는 구성) ──
    AI_MODEL_NOT_LOADED = ("AI_MODEL_NOT_LOADED", "AI 모델이 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요.", 503)
    AI_MODEL_OUT_OF_MEMORY = ("AI_MODEL_OUT_OF_MEMORY", "AI 처리 자원이 부족합니다. 잠시 후 다시 시도해 주세요.", 503)
    AI_INVALID_RESPONSE = ("AI_INVALID_RESPONSE", "AI 응답을 해석할 수 없습니다.", 502)
    AI_ANALYZER_FAILED = ("AI_ANALYZER_FAILED", "일부 분석에 실패했습니다.", 502)

    INTERNAL_ERROR = ("INTERNAL_ERROR", "서버 내부 오류가 발생했습니다.", 500)

    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code

# =============================================================================
# 이 파일의 책임: documents.status / extracted_texts.extract_method /
#   analyses.analyzer_type 컬럼에 들어갈 수 있는 값의 집합을 코드로 고정한다.
#   DB 컬럼 자체는 문자열(String)이고, 이 Enum은 코드에서 오타 없이 값을
#   참조하기 위한 상수 모음이다 (DB에 별도 ENUM 타입/테이블을 만들지 않는다).

# 다른 파일과의 관계: models/document.py, services/* 에서 이 Enum의 .value를
#   문자열 컬럼에 그대로 저장한다. document_type은 처음에 "값이 계속 늘어날 수
#   있다"는 이유로 Enum 없이 자유 문자열로 두었으나, 도메인을 공공 SI·용역
#   사업으로 좁히면서 9종으로 확정했으므로 DocumentType Enum을 둔다. DB 컬럼은
#   여전히 String이고 값 제한은 CHECK 제약으로 넣는다(리비전 0008 예정).
#   CREATE TYPE AS ENUM을 쓰지 않으므로 값이 늘어도 ALTER TYPE이 필요 없다.

# Spring 비교: Java enum + @Enumerated(EnumType.STRING)과 같은 목적.
#   차이는 여기서는 SQLAlchemy 컬럼 타입을 Enum으로 강제하지 않고 일반
#   String 컬럼에 .value 문자열만 저장한다는 점 — 마이그레이션(Alembic) 없이
#   값이 추가/변경되어도 스키마 변경이 필요 없도록 하기 위함이다.
# =============================================================================

from enum import Enum


class DocumentStatus(str, Enum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    ANALYZING = "ANALYZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ExtractMethod(str, Enum):
    TEXT_LAYER = "TEXT_LAYER"
    OCR = "OCR"
    DOCX = "DOCX"
    HWPX = "HWPX"
    HYBRID = "HYBRID"


# 분석기 4종. 문서 유형과 무관하게 항상 전부 실행한다.
# 유형별로 골라 쓰는 방식은 폐기했다(구판 ANL-04 — v5 에 후속 항목이 없다).
# 분류 결과를 기다려야 해서 병렬 실행이 깨지고, 회의록·보고서에도 금액이
# 나오는데 놓치기 때문이다.
class AnalyzerType(str, Enum):
    SUMMARY = "summary"
    CATEGORY = "category"
    EXTRACT = "extract"    # 액션아이템·결정사항·일정 (ANL-002-1·2·3)
    AMOUNT = "amount"      # 금액 항목 (AMT-001-1). 전용 모델·어댑터를 쓴다


class MemberRole(str, Enum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ProcessingMode(str, Enum):
    NORMAL = "NORMAL"
    REVIEW = "REVIEW"


class ReviewStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class OcrElementType(str, Enum):
    TEXT_LINE = "TEXT_LINE"
    HEADING = "HEADING"
    TABLE_ROW = "TABLE_ROW"
    TABLE_HEADER = "TABLE_HEADER"
    HEADER_FOOTER = "HEADER_FOOTER"


class OcrElementTypeSource(str, Enum):
    AUTO = "AUTO"
    USER = "USER"
    USER_CORRECTED = "USER_CORRECTED"


class ExtractionStrategy(str, Enum):
    AUTO = "AUTO"
    TEXT_ONLY = "TEXT_ONLY"
    TEXT_WITH_IMAGE_OCR = "TEXT_WITH_IMAGE_OCR"
    
    

# =============================================================================
# 문서 유형 — 도메인: 공공 SI · 용역 사업
#
# 9종 전부가 금액과 관계가 있다. 도메인을 좁힌 효과다. 범용이었을 때는
# MANUAL 처럼 금액이 없는 유형이 섞여 있었다.
# 업로드 시 사용자가 지정하고(document_type_source=USER), 지정하지 않으면
# 분류 분석기가 채운다(AI). 사람이 AI 판별을 고친 비율(USER_CORRECTED)이
# 곧 분류 오류율이 되어 별도 정답셋 없이 정확도를 잴 수 있다.
# =============================================================================
class DocumentType(str, Enum):
    RFP = "RFP"                          # 제안요청서 · 입찰공고
    PROPOSAL = "PROPOSAL"                # 제안서 · 기술제안서
    COST_SHEET = "COST_SHEET"            # 산출내역서 · 견적서 · 원가계산서
    CONTRACT = "CONTRACT"                # 계약서 · 과업지시서 · 착수신고서
    CONTRACT_CHANGE = "CONTRACT_CHANGE"  # 변경계약서 · 과업변경합의서
    REPORT = "REPORT"                    # 착수 · 주간 · 월간 · 완료보고서 · 검사조서
    MEETING_NOTES = "MEETING_NOTES"      # 회의록
    BILLING = "BILLING"                  # 대가지급청구서 · 세금계산서
    ETC = "ETC"

class DocumentTypeSource(str, Enum):
    USER = "USER"                        # 업로드 시 사람이 지정
    AI = "AI"                            # 분류 분석기가 판별
    USER_CORRECTED = "USER_CORRECTED"    # AI 판별을 사람이 고침 → 오류율의 분자

# =============================================================================
# 금액 항목의 원가 구분 — 공공 SI 사업 원가 구조
#
# VAT 를 반드시 구분해야 한다. 부가세를 다른 항목과 똑같이 넣으면 항목 합계를
# 낼 때 이중으로 더해진다. 합계 대조(AMT-002-1)가 틀리는 가장 흔한 원인이다.
# 그래서 amount_calculator.sum_items() 는 VAT 를 제외하고 더한다.
# =============================================================================
class AmountCategory(str, Enum):
    DIRECT_LABOR = "DIRECT_LABOR"    # 직접인건비
    EXPENSE = "EXPENSE"              # 직접경비 (여비 · 수용비 등)
    OVERHEAD = "OVERHEAD"            # 제경비
    TECH_FEE = "TECH_FEE"            # 기술료
    MATERIAL = "MATERIAL"            # 재료비 · 물품비
    SUBCONTRACT = "SUBCONTRACT"      # 외주비
    VAT = "VAT"                      # 부가가치세 — 항목 합계에서 제외한다
    OTHER = "OTHER"

# =============================================================================
# AI 제안의 승인 상태 — amount_items · decisions · schedule_items 가 공유한다
#
# 승인해야 반영된다. AI 가 뽑은 것을 자동 등록하지 않는다. 틀린 항목이 바로
# 들어가면 사용자가 도구를 신뢰하지 않게 되기 때문이다(TSK-002-1 자동 등록 금지).
# EDITED 는 사람이 값을 고쳐서 승인한 경우다. 채택률 지표에서 APPROVED 와
# 구분해야 "AI 가 그대로 쓸 만했는가" 를 알 수 있다.
# =============================================================================
class SuggestionDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"


# =============================================================================
# 이 파일의 책임: documents.status / extracted_texts.extract_method /
#   analyses.analyzer_type 컬럼에 들어갈 수 있는 값의 집합을 코드로 고정한다.
#   DB 컬럼 자체는 문자열(String)이고, 이 Enum은 코드에서 오타 없이 값을
#   참조하기 위한 상수 모음이다 (DB에 별도 ENUM 타입/테이블을 만들지 않는다).
# 다른 파일과의 관계: models/document.py, services/* 에서 이 Enum의 .value를
#   문자열 컬럼에 그대로 저장한다. document_type(문서 종류: general 등)은
#   본프로젝트에서 값이 계속 늘어날 수 있어 이 파일에 Enum으로 두지 않고
#   documents.document_type을 자유 문자열 컬럼으로만 둔다 (§2-2 참고).
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


class AnalyzerType(str, Enum):
    SUMMARY = "summary"
    CATEGORY = "category"


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


class ExtractionStrategy(str, Enum):
    AUTO = "AUTO"
    TEXT_ONLY = "TEXT_ONLY"
    TEXT_WITH_IMAGE_OCR = "TEXT_WITH_IMAGE_OCR"

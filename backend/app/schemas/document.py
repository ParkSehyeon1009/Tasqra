# =============================================================================
# 이 파일의 책임: 문서 업로드/분석/목록/상세 API의 요청·응답 Pydantic 스키마를
#   정의한다 (§7 API 계약 그대로). 필드명은 모두 snake_case이며 camelCase로
#   변환하지 않는다 — 프론트(React)도 snake_case 그대로 사용하기로 합의됨.
# 다른 파일과의 관계: models/document.py(Document/ExtractedText/Analysis)의
#   ORM 인스턴스를 이 스키마로 변환해 라우터가 응답한다 (services/*가 담당,
#   담당자 A/B/C가 구현). result 필드는 분석기마다 구조가 달라 dict[str, Any]로
#   열어두어, 분석기가 추가돼도 API 응답 스펙(analyses[].result의 타입)이
#   바뀌지 않게 한다.
# Spring 비교: @RestController가 반환하는 Response DTO 클래스들과 동일한 역할.
#   model_config(from_attributes=True)는 Spring에서 Entity -> DTO를 변환할 때
#   흔히 쓰는 정적 팩토리(예: DocumentResponse.from(entity))를, Pydantic이
#   Model.model_validate(orm_instance) 한 줄로 대신해주는 것과 같다.
# =============================================================================

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    filename: str
    file_type: str
    document_type: str | None
    document_type_source: str | None
    extraction_strategy: str
    status: str
    processing_error: str | None
    review_status: str
    page_count: int | None
    char_count: int | None
    text_char_count: int
    ocr_char_count: int
    extract_method: str | None
    created_at: datetime


class AnalyzeRequest(BaseModel):
    # 생략 시(None) 서비스 레이어가 기본으로 summary/category 둘 다 실행한다.
    analyzer_types: list[str] | None = None


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analyzer_type: str
    result: dict[str, Any] = Field(validation_alias="result_json")
    provider: str
    model_name: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    source_text_revision: int
    created_at: datetime


class AnalyzeResponse(BaseModel):
    document_id: int
    analyses: list[AnalysisResponse]


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    document_type: str | None
    status: str
    processing_error: str | None = None
    review_status: str
    page_count: int | None = None
    char_count: int | None = None
    text_char_count: int | None = None
    ocr_char_count: int = 0
    extract_method: str | None = None
    category: str | None = None
    summary_preview: str | None = None
    created_at: datetime


class DocumentDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    filename: str
    file_type: str
    document_type: str | None
    status: str
    processing_error: str | None = None
    review_status: str
    extraction_strategy: str
    uploaded_by_name: str | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    extracted_text: str | None = None
    page_count: int | None = None
    char_count: int | None = None
    extract_method: str | None = None
    text_version: int | None = None
    is_confirmed: bool = False
    analyses: list[AnalysisResponse] = []


class OcrRevisionResponse(BaseModel):
    id: int
    element_id: int
    changed_by_name: str | None = None
    before_text: str
    after_text: str
    from_version: int
    to_version: int
    created_at: datetime


class OcrElementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_text: str
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float | None
    source: str
    element_type: str
    element_type_source: str
    is_paragraph_start: bool
    table_id: int | None
    table_row: int | None
    reading_order: int
    version: int
    is_excluded: bool
    content_start: int | None
    content_end: int | None
    is_in_content: bool


class OcrPageResponse(BaseModel):
    id: int
    page_number: int
    page_kind: str
    width: int
    height: int
    image_url: str
    elements: list[OcrElementResponse]


class OcrReviewResponse(BaseModel):
    document_id: int
    review_status: str
    ocr_revision: int
    ocr_char_count: int
    pages: list[OcrPageResponse]


class OcrElementUpdateRequest(BaseModel):
    text: str = Field(max_length=10000)
    version: int = Field(ge=1)


class OcrElementExclusionRequest(BaseModel):
    is_excluded: bool
    version: int = Field(ge=1)


class OcrElementBatchUpdateItem(BaseModel):
    id: int = Field(ge=1)
    version: int = Field(ge=1)
    text: str | None = Field(default=None, max_length=10000)
    is_excluded: bool | None = None
    is_paragraph_start: bool | None = None
    element_type: str | None = Field(
        default=None,
        pattern="^(TEXT_LINE|HEADING|TABLE_ROW|TABLE_HEADER|HEADER_FOOTER)$",
    )

    @model_validator(mode="after")
    def require_change(self):
        if all(value is None for value in (self.text, self.is_excluded, self.is_paragraph_start, self.element_type)):
            raise ValueError("at least one editable field is required")
        return self


class OcrElementBatchUpdateRequest(BaseModel):
    items: list[OcrElementBatchUpdateItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_unique_ids(self):
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate OCR element ids are not allowed")
        return self


class OcrElementBatchUpdateResponse(BaseModel):
    ocr_revision: int
    text_version: int | None
    items: list[OcrElementResponse]

from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DocumentStatus, ProcessingMode, ReviewStatus


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_size >= 0", name="ck_document_file_size"),
        CheckConstraint("ocr_revision >= 1", name="ck_document_ocr_revision"),
        Index("ix_doc_list", "project_id", "created_at"),
        Index("ix_doc_type", "project_id", "document_type"),
        Index("ix_doc_package", "project_id", "package_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    document_type: Mapped[str | None] = mapped_column(String(30))
    document_type_source: Mapped[str | None] = mapped_column(String(20))
    package_key: Mapped[str | None] = mapped_column(String(500))
    package_role: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DocumentStatus.PENDING.value)
    processing_error: Mapped[str | None] = mapped_column(String(1000))
    processing_mode: Mapped[str] = mapped_column(String(20), nullable=False, default=ProcessingMode.NORMAL.value)
    extraction_strategy: Mapped[str] = mapped_column(String(30), nullable=False, default="AUTO")
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default=ReviewStatus.NOT_REQUIRED.value)
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    ocr_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    category_cache: Mapped[str | None] = mapped_column(String(30))
    summary_preview: Mapped[str | None] = mapped_column(String(300))
    # 문서 아래쪽 「합계」 칸에 적힌 값. 우리가 항목을 더한 합계와 대조하는 기준이다
    # (AMT-002-1). 리비전 0022.
    #
    # NULL 이 정상이다 — 합계가 적혀 있지 않은 문서가 있다(공고문·계약서 본문).
    # 0 을 넣으면 "합계가 0원" 과 "안 적혀 있다" 를 구별할 수 없고 대조가 항상
    # 불일치로 나온다. amount_calculator.TotalCheck 가 None 을 「대조 불가」로
    # 따로 다루는 것과 같은 이유다.
    #
    # 형이 amount_items.amount 와 같다(Numeric(18,2)). 다르면 계산기에 넘길 때
    # 변환 규칙이 둘이 되어 반올림이 어긋난다.
    stated_total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="documents")
    uploader = relationship("User", foreign_keys=[uploaded_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    extracted_text = relationship("ExtractedText", back_populates="document", uselist=False, cascade="all, delete-orphan")
    analyses = relationship("Analysis", back_populates="document", cascade="all, delete-orphan")
    review_pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.seq")

    @property
    def stored_path(self) -> str:
        return self.storage_path

    @property
    def active_ocr_char_count(self) -> int:
        return self.extracted_text.ocr_char_count if self.extracted_text else 0

    @property
    def native_text_char_count(self) -> int:
        return self.extracted_text.text_char_count if self.extracted_text else 0


class ExtractedText(Base):
    __tablename__ = "extracted_texts"
    __table_args__ = (
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="ck_extracted_page_count"),
        CheckConstraint("char_count IS NULL OR char_count >= 0", name="ck_extracted_char_count"),
        CheckConstraint("text_char_count >= 0", name="ck_extracted_text_char_count"),
        CheckConstraint("ocr_char_count >= 0", name="ck_extracted_ocr_char_count"),
        CheckConstraint("text_version >= 1", name="ck_extracted_text_version"),
    )

    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    char_count: Mapped[int | None] = mapped_column(Integer)
    text_char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extract_method: Mapped[str | None] = mapped_column(String(20))
    text_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    document = relationship("Document", back_populates="extracted_text")


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="PAGE")
    image_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)

    document = relationship("Document", back_populates="review_pages")
    elements = relationship("OcrElement", back_populates="page", cascade="all, delete-orphan", order_by="OcrElement.reading_order")


class OcrElement(Base):
    __tablename__ = "ocr_elements"
    __table_args__ = (
        CheckConstraint("x >= 0 AND x <= 1 AND y >= 0 AND y <= 1", name="ck_ocr_element_origin"),
        CheckConstraint("width >= 0 AND width <= 1 AND height >= 0 AND height <= 1", name="ck_ocr_element_size"),
        CheckConstraint("version >= 1", name="ck_ocr_element_version"),
        CheckConstraint("content_start IS NULL OR content_start >= 0", name="ck_ocr_element_content_start"),
        CheckConstraint("content_end IS NULL OR content_end >= content_start", name="ck_ocr_element_content_end"),
        CheckConstraint("element_type IN ('TEXT_LINE', 'HEADING', 'TABLE_ROW', 'TABLE_HEADER', 'HEADER_FOOTER')", name="ck_ocr_element_type"),
        CheckConstraint("element_type_source IN ('AUTO', 'USER', 'USER_CORRECTED')", name="ck_ocr_element_type_source"),
        CheckConstraint("table_id IS NULL OR table_id >= 0", name="ck_ocr_element_table_id"),
        CheckConstraint("table_row IS NULL OR table_row >= 0", name="ck_ocr_element_table_row"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    page_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False, index=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="OCR")
    element_type: Mapped[str] = mapped_column(String(20), nullable=False, default="TEXT_LINE")
    element_type_source: Mapped[str] = mapped_column(String(20), nullable=False, default="AUTO")
    is_paragraph_start: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    table_id: Mapped[int | None] = mapped_column(Integer)
    table_row: Mapped[int | None] = mapped_column(Integer)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_start: Mapped[int | None] = mapped_column(Integer)
    content_end: Mapped[int | None] = mapped_column(Integer)
    is_in_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    page = relationship("DocumentPage", back_populates="elements")
    revisions = relationship("OcrElementRevision", back_populates="element", cascade="all, delete-orphan")


class OcrElementRevision(Base):
    __tablename__ = "ocr_element_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ocr_elements.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    before_text: Mapped[str] = mapped_column(Text, nullable=False)
    after_text: Mapped[str] = mapped_column(Text, nullable=False)
    from_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    element = relationship("OcrElement", back_populates="revisions")


class OcrMergeOperation(Base):
    __tablename__ = "ocr_merge_operations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    survivor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ocr_elements.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    snapshot_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    merged_version: Mapped[int] = mapped_column(Integer, nullable=False)
    undone_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OcrStructureEvent(Base):
    __tablename__ = "ocr_structure_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    details_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (Index("ix_analysis_doc_type", "document_id", "analyzer_type"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    analyzer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    source_text_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    document = relationship("Document", back_populates="analyses")

    @property
    def result(self) -> dict:
        return self.result_json

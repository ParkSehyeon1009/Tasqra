import hashlib
import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.extractors.protocol import ExtractResult
from app.extractors.registry import ExtractorRegistry
from app.extractors.structure import detect_header_footer, detect_heading
from app.models.document import Document, DocumentPage, ExtractedText, OcrElement
from app.models.enums import DocumentStatus, DocumentType, DocumentTypeSource, ExtractionStrategy, OcrElementType, OcrElementTypeSource, ProcessingMode, ReviewStatus
from app.repositories.document_repository import DocumentRepository

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".hwpx", ".png", ".jpg", ".jpeg"}


class ExtractionService:
    def __init__(self, db: Session, document_repository: DocumentRepository, extractor_registry: ExtractorRegistry) -> None:
        self._db = db
        self._document_repository = document_repository
        self._extractor_registry = extractor_registry

    def create_pending_upload(
        self,
        project_id: int,
        uploaded_by: int,
        filename: str,
        content: bytes,
        extraction_strategy: str = "AUTO",
        document_type: str | None = None,
    ) -> Document:
        safe_filename = self._sanitize_filename(filename)
        extension = Path(safe_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise BusinessError(ErrorCode.INVALID_FILE_TYPE, detail="PDF, DOCX, HWPX, PNG, JPG, JPEG 파일만 업로드할 수 있습니다.")
        if len(content) > settings.max_file_size_bytes:
            raise BusinessError(ErrorCode.FILE_TOO_LARGE, detail=f"파일은 최대 {settings.MAX_FILE_SIZE_MB}MB까지 업로드할 수 있습니다.")
        if not content:
            raise BusinessError(ErrorCode.EXTRACTION_FAILED, detail="빈 파일은 업로드할 수 없습니다.")

        file_type = extension.lstrip(".")
        strategy = self._validate_extraction_strategy(file_type, extraction_strategy)
        selected_document_type = self._validate_document_type(document_type)
        content_hash = hashlib.sha256(content).hexdigest()
        duplicate = self._document_repository.get_by_content_hash(project_id, content_hash)
        if duplicate is not None:
            raise BusinessError(ErrorCode.DUPLICATE_DOCUMENT, detail=f"동일한 내용의 문서 '{duplicate.filename}'이(가) 이미 등록되어 있습니다.")

        stored_path = self._save_file(extension, content)
        try:
            with transactional(self._db):
                document = self._document_repository.create(Document(
                    project_id=project_id,
                    uploaded_by=uploaded_by,
                    filename=safe_filename,
                    storage_path=stored_path,
                    file_type=file_type,
                    file_size=len(content),
                    content_hash=content_hash,
                    document_type=selected_document_type.value if selected_document_type else None,
                    document_type_source=DocumentTypeSource.USER.value if selected_document_type else None,
                    status=DocumentStatus.PENDING.value,
                    processing_error=None,
                    extraction_strategy=strategy.value,
                    processing_mode=ProcessingMode.NORMAL.value,
                    review_status=ReviewStatus.NOT_REQUIRED.value,
                ))
            return document
        except Exception:
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise

    def process_document(self, project_id: int, document_id: int) -> Document:
        document = self._document_repository.get_by_id(project_id, document_id)
        if document is None:
            raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
        if document.status == DocumentStatus.EXTRACTED.value:
            return document

        document.status = DocumentStatus.EXTRACTING.value
        document.processing_error = None
        self._db.commit()
        review_paths: list[str] = []

        try:
            result = self._extract(document)
            self._validate_result(document.file_type, result)
            with transactional(self._db):
                document.extracted_text = ExtractedText(
                    content=result.content,
                    page_count=result.page_count,
                    char_count=result.char_count,
                    text_char_count=result.text_char_count,
                    ocr_char_count=result.ocr_char_count,
                    extract_method=result.extract_method,
                )
                self._attach_review_pages(document, result, review_paths)
                document.processing_mode = ProcessingMode.REVIEW.value if result.review_pages else ProcessingMode.NORMAL.value
                document.review_status = ReviewStatus.PENDING.value if result.review_pages else ReviewStatus.NOT_REQUIRED.value
                document.status = DocumentStatus.EXTRACTED.value
                document.processing_error = None
            return document
        except Exception as exc:
            self._db.rollback()
            failed = self._document_repository.get_by_id(project_id, document_id)
            if failed is not None:
                failed.status = DocumentStatus.FAILED.value
                failed.processing_error = self._error_message(exc)[:1000]
                self._db.commit()
            for path in review_paths:
                if os.path.exists(path):
                    os.remove(path)
            raise

    def discard_pending_upload(self, document: Document) -> None:
        stored_path = document.storage_path
        with transactional(self._db):
            self._document_repository.delete(document)
        if os.path.exists(stored_path):
            os.remove(stored_path)

    def prepare_retry(self, project_id: int, document_id: int) -> Document:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            if document.status != DocumentStatus.FAILED.value:
                raise BusinessError(ErrorCode.DOCUMENT_RETRY_NOT_ALLOWED)
            document.status = DocumentStatus.PENDING.value
            document.processing_error = None
        return document

    def mark_queue_failure(self, project_id: int, document_id: int) -> None:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update(project_id, document_id)
            if document is not None:
                document.status = DocumentStatus.FAILED.value
                document.processing_error = ErrorCode.PROCESS_QUEUE_UNAVAILABLE.message

    def upload_and_extract(
        self,
        project_id: int,
        uploaded_by: int,
        filename: str,
        content: bytes,
        extraction_strategy: str = "AUTO",
        document_type: str | None = None,
    ) -> Document:
        """Synchronous compatibility entry point used by tests and scripts."""
        document = self.create_pending_upload(project_id, uploaded_by, filename, content, extraction_strategy, document_type)
        return self.process_document(project_id, document.id)

    def _extract(self, document: Document) -> ExtractResult:
        extractor = self._extractor_registry.get(document.file_type)
        strategy = ExtractionStrategy(document.extraction_strategy)
        try:
            if document.file_type in {"docx", "hwpx"}:
                result = extractor.extract(document.storage_path, include_image_ocr=strategy is not ExtractionStrategy.TEXT_ONLY)
            elif document.file_type == "pdf":
                result = extractor.extract(document.storage_path, extraction_strategy=strategy.value)
            else:
                result = extractor.extract(document.storage_path)
        except BusinessError:
            raise
        except Exception as exc:
            raise BusinessError(ErrorCode.EXTRACTION_FAILED) from exc
        return result

    @staticmethod
    def _validate_result(file_type: str, result: ExtractResult) -> None:
        if not result.content.strip():
            raise BusinessError(ErrorCode.EXTRACTION_FAILED, detail="문서에서 추출할 수 있는 텍스트가 없습니다.")
        if file_type == "pdf" and result.page_count > settings.MAX_PAGES:
            raise BusinessError(ErrorCode.TOO_MANY_PAGES, detail=f"PDF는 최대 {settings.MAX_PAGES}페이지까지 업로드할 수 있습니다.")
        if file_type in {"docx", "hwpx"} and result.char_count > settings.MAX_EXTRACTED_CHARS:
            raise BusinessError(ErrorCode.CONTENT_TOO_LARGE, detail=f"DOCX와 HWPX는 추출 텍스트를 최대 {settings.MAX_EXTRACTED_CHARS:,}자까지 허용합니다.")

    def _attach_review_pages(self, document: Document, result: ExtractResult, review_paths: list[str]) -> None:
        header_footer_elements = detect_header_footer([
            [(element.text, element.y) for element in page.elements]
            for page in result.review_pages
        ])
        content_cursor = 0
        for page_index, page_result in enumerate(result.review_pages):
            page_path = self._save_review_image(document.id, page_result.page_number, page_result.image_bytes)
            review_paths.append(page_path)
            page = DocumentPage(page_number=page_result.page_number, page_kind=page_result.page_kind, image_path=page_path, width=page_result.width, height=page_result.height)
            for index, item in enumerate(page_result.elements):
                element_type = item.element_type
                element_type_source = item.element_type_source
                is_paragraph_start = item.is_paragraph_start
                if element_type == OcrElementType.TEXT_LINE.value:
                    element_type_source = OcrElementTypeSource.AUTO.value
                    if (page_index, index) in header_footer_elements:
                        element_type = OcrElementType.HEADER_FOOTER.value
                        is_paragraph_start = False
                    elif detect_heading(item.text):
                        element_type = OcrElementType.HEADING.value
                        is_paragraph_start = True
                content_start = item.content_start if item.content_start is not None else result.content.find(item.text, content_cursor)
                content_end = item.content_end if item.content_end is not None else content_start + len(item.text) if content_start >= 0 else None
                if content_end is not None:
                    content_cursor = content_end
                page.elements.append(OcrElement(
                    original_text=item.text, text=item.text, x=item.x, y=item.y, width=item.width, height=item.height,
                    confidence=item.confidence, source=item.source, element_type=element_type,
                    element_type_source=element_type_source, is_paragraph_start=is_paragraph_start,
                    table_id=item.table_id, table_row=item.table_row, reading_order=index,
                    content_start=content_start if content_start >= 0 else None, content_end=content_end, is_in_content=True,
                ))
            document.review_pages.append(page)

    @staticmethod
    def _error_message(exc: Exception) -> str:
        if isinstance(exc, BusinessError):
            return exc.detail or exc.error_code.message
        return "문서 처리 중 예상하지 못한 오류가 발생했습니다."

    @staticmethod
    def _validate_extraction_strategy(file_type: str, value: str) -> ExtractionStrategy:
        try:
            strategy = ExtractionStrategy(value.upper())
        except (AttributeError, ValueError) as exc:
            raise BusinessError(ErrorCode.INVALID_EXTRACTION_STRATEGY) from exc
        if file_type in {"png", "jpg", "jpeg"} and strategy is not ExtractionStrategy.AUTO:
            raise BusinessError(ErrorCode.INVALID_EXTRACTION_STRATEGY)
        return strategy

    @staticmethod
    def _validate_document_type(value: str | None) -> DocumentType | None:
        if value is None or not value.strip():
            return None
        try:
            return DocumentType(value.strip().upper())
        except ValueError as exc:
            raise BusinessError(ErrorCode.INVALID_DOCUMENT_TYPE) from exc

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        safe_filename = filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip()
        if not safe_filename or safe_filename in {".", ".."}:
            raise BusinessError(ErrorCode.INVALID_FILE_TYPE, detail="올바른 파일명이 필요합니다.")
        return safe_filename

    @staticmethod
    def _save_file(extension: str, content: bytes) -> str:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        stored_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4().hex}{extension}")
        with open(stored_path, "wb") as file:
            file.write(content)
        return stored_path

    @staticmethod
    def _save_review_image(document_id: int, page_number: int, content: bytes) -> str:
        directory = os.path.join(settings.UPLOAD_DIR, "review", str(document_id))
        os.makedirs(directory, exist_ok=True)
        stored_path = os.path.join(directory, f"{page_number}.png")
        with open(stored_path, "wb") as file:
            file.write(content)
        return stored_path

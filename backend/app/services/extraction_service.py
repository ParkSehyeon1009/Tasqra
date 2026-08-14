import hashlib
import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.extractors.registry import ExtractorRegistry
from app.models.document import Document, DocumentPage, ExtractedText, OcrElement
from app.models.enums import DocumentStatus, DocumentType, DocumentTypeSource, ExtractionStrategy, ProcessingMode, ReviewStatus
from app.repositories.document_repository import DocumentRepository

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".hwpx", ".png", ".jpg", ".jpeg"}


class ExtractionService:
    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository,
        extractor_registry: ExtractorRegistry,
    ) -> None:
        self._db = db
        self._document_repository = document_repository
        self._extractor_registry = extractor_registry

    def upload_and_extract(
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
            raise BusinessError(
                ErrorCode.INVALID_FILE_TYPE,
                detail="PDF, DOCX, HWPX, PNG, JPG, JPEG 파일만 업로드할 수 있습니다.",
            )
        # 라우터를 거치지 않고 서비스가 직접 호출되는 경우에도
        # 최대 파일 크기를 반드시 검증한다.
        if len(content) > settings.max_file_size_bytes:
            raise BusinessError(
                ErrorCode.FILE_TOO_LARGE,
                detail=f"파일은 최대 {settings.MAX_FILE_SIZE_MB}MB까지 업로드할 수 있습니다.",
            )

        if not content:
            raise BusinessError(
                ErrorCode.EXTRACTION_FAILED,
                detail="빈 파일은 업로드할 수 없습니다.",
            )

        content_hash = hashlib.sha256(content).hexdigest()
        duplicate = self._document_repository.get_by_content_hash(project_id, content_hash)
        if duplicate is not None:
            raise BusinessError(
                ErrorCode.DUPLICATE_DOCUMENT,
                detail=f"동일한 내용의 문서 '{duplicate.filename}'이(가) 이미 등록되어 있습니다.",
            )

        stored_path = self._save_file(extension, content)
        review_paths: list[str] = []

        try:
            file_type = extension.lstrip(".")
            extractor = self._extractor_registry.get(file_type)

            strategy = self._validate_extraction_strategy(file_type, extraction_strategy)
            selected_document_type = self._validate_document_type(document_type)

            try:
                if file_type in {"docx", "hwpx"}:
                    result = extractor.extract(
                        stored_path,
                        include_image_ocr=strategy is not ExtractionStrategy.TEXT_ONLY,
                    )
                elif file_type == "pdf":
                    result = extractor.extract(
                        stored_path,
                        extraction_strategy=strategy.value,
                    )
                else:
                    result = extractor.extract(stored_path)

                if not result.content.strip():
                    raise BusinessError(
                        ErrorCode.EXTRACTION_FAILED,
                        detail="문서에서 추출할 수 있는 텍스트가 없습니다.",
                    )
            except BusinessError:
                raise
            except Exception as exc:
                raise BusinessError(ErrorCode.EXTRACTION_FAILED) from exc

            if file_type == "pdf" and result.page_count > settings.MAX_PAGES:
                raise BusinessError(
                    ErrorCode.TOO_MANY_PAGES,
                    detail=f"PDF는 최대 {settings.MAX_PAGES}페이지까지 업로드할 수 있습니다.",
                )

            if (
                file_type in {"docx", "hwpx"}
                and result.char_count > settings.MAX_EXTRACTED_CHARS
            ):
                raise BusinessError(
                    ErrorCode.CONTENT_TOO_LARGE,
                    detail=(
                        "DOCX와 HWPX는 추출된 텍스트가 "
                        f"최대 {settings.MAX_EXTRACTED_CHARS:,}자까지 허용됩니다."
                    ),
                )

            with transactional(self._db):
                document = self._document_repository.create(
                    Document(
                        project_id=project_id,
                        uploaded_by=uploaded_by,
                        # 사용자에게 표시할 원래 파일명
                        filename=safe_filename,
                        # UUID 기반 실제 저장 경로
                        storage_path=stored_path,
                        file_type=file_type,
                        file_size=len(content),
                        content_hash=content_hash,
                        document_type=selected_document_type.value if selected_document_type else None,
                        document_type_source=DocumentTypeSource.USER.value if selected_document_type else None,
                        status=DocumentStatus.EXTRACTED.value,
                        extraction_strategy=strategy.value,
                        processing_mode=ProcessingMode.REVIEW.value if result.review_pages else ProcessingMode.NORMAL.value,
                        review_status=ReviewStatus.PENDING.value if result.review_pages else ReviewStatus.NOT_REQUIRED.value,
                    )
                )
                document.extracted_text = ExtractedText(
                    content=result.content,
                    page_count=result.page_count,
                    char_count=result.char_count,
                    text_char_count=result.text_char_count,
                    ocr_char_count=result.ocr_char_count,
                    extract_method=result.extract_method,
                )
                content_cursor = 0
                for page_result in result.review_pages:
                    page_path = self._save_review_image(document.id, page_result.page_number, page_result.image_bytes)
                    review_paths.append(page_path)
                    page = DocumentPage(page_number=page_result.page_number, page_kind=page_result.page_kind, image_path=page_path, width=page_result.width, height=page_result.height)
                    page.elements = []
                    for index, item in enumerate(page_result.elements):
                        content_start = item.content_start if item.content_start is not None else result.content.find(item.text, content_cursor)
                        content_end = item.content_end if item.content_end is not None else content_start + len(item.text) if content_start >= 0 else None
                        if content_end is not None:
                            content_cursor = content_end
                        page.elements.append(OcrElement(original_text=item.text, text=item.text, x=item.x, y=item.y, width=item.width, height=item.height, confidence=item.confidence, source=item.source, element_type=item.element_type, element_type_source=item.element_type_source, is_paragraph_start=item.is_paragraph_start, table_id=item.table_id, table_row=item.table_row, reading_order=index, content_start=content_start if content_start >= 0 else None, content_end=content_end, is_in_content=True))
                    document.review_pages.append(page)

            return document
        except Exception:
            # 추출, 페이지 검증 또는 DB 저장 중 실패하면 이미 저장된
            # 원본 파일을 삭제해 고아 파일이 남지 않게 한다.
            if os.path.exists(stored_path):
                os.remove(stored_path)
            for path in review_paths:
                if os.path.exists(path):
                    os.remove(path)
            raise

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
        # Windows와 POSIX 형식의 경로 부분을 모두 제거한다.
        normalized = filename.replace("\\", "/")
        safe_filename = normalized.rsplit("/", maxsplit=1)[-1].strip()

        if not safe_filename or safe_filename in {".", ".."}:
            raise BusinessError(
                ErrorCode.INVALID_FILE_TYPE,
                detail="올바른 파일명이 필요합니다.",
            )

        return safe_filename

    @staticmethod
    def _save_file(extension: str, content: bytes) -> str:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

        # 사용자 입력 파일명을 실제 저장 경로에 포함하지 않는다.
        # 같은 이름의 파일이 여러 번 올라와도 UUID가 달라 충돌하지 않는다.
        unique_name = f"{uuid.uuid4().hex}{extension}"
        stored_path = os.path.join(settings.UPLOAD_DIR, unique_name)

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

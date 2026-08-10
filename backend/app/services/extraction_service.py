import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.extractors.registry import ExtractorRegistry
from app.models.document import Document, ExtractedText
from app.models.enums import DocumentStatus
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

    def upload_and_extract(self, filename: str, content: bytes) -> Document:
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

        stored_path = self._save_file(extension, content)

        try:
            file_type = extension.lstrip(".")
            extractor = self._extractor_registry.get(file_type)

            try:
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
                        # 사용자에게 표시할 원래 파일명
                        filename=safe_filename,
                        # UUID 기반 실제 저장 경로
                        stored_path=stored_path,
                        file_type=file_type,
                        file_size=len(content),
                        status=DocumentStatus.EXTRACTED.value,
                    )
                )
                document.extracted_text = ExtractedText(
                    content=result.content,
                    page_count=result.page_count,
                    char_count=result.char_count,
                    extract_method=result.extract_method,
                )

            return document
        except Exception:
            # 추출, 페이지 검증 또는 DB 저장 중 실패하면 이미 저장된
            # 원본 파일을 삭제해 고아 파일이 남지 않게 한다.
            if os.path.exists(stored_path):
                os.remove(stored_path)
            raise

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

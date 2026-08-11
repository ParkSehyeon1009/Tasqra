# =============================================================================
# 이 파일의 책임: 문서 목록 조회/검색, 상세 조회, 요약 텍스트 다운로드에 필요한
#   비즈니스 로직을 담당한다 (지시서 플로우 ⑦ 결과 화면 · ⑧ 결과 파일 다운로드).
#   DB 세션을 직접 다루지 않고 DocumentRepository / AnalysisRepository를 거친다.
# 다른 파일과의 관계: dependencies.py의 get_document_service()가 Repository들을
#   주입해 이 클래스를 생성한다. api/routes/document_router.py가 이 서비스를
#   호출하고, 반환된 데이터를 schemas/document.py의 응답 스키마로 변환한다.
#   목록의 category / summary_preview 값은 analyses 테이블의 최신 분석 결과
#   (analyzer_type = "category" / "summary")의 result_json에서 꺼내온다.
# Spring 비교: @Service 클래스와 동일한 위치. Repository를 생성자 주입으로 받고
#   Controller에는 Entity가 아닌 가공된 값을 넘긴다. 조회 전용이라 @Transactional
#   (여기서는 transactional 컨텍스트매니저)을 쓰지 않는다.
# =============================================================================

import logging
import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.document import Document, OcrElementRevision
from app.models.enums import AnalyzerType, ReviewStatus
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.document_repository import DocumentRepository

# 목록 화면에 보여줄 요약 미리보기 길이. 전문은 상세 조회에서 확인한다.
SUMMARY_PREVIEW_LENGTH = 100

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class DocumentListRow:
    """목록 한 줄에 필요한 값 묶음.

    Service가 스키마(Pydantic)를 직접 만들지 않고 이 객체를 반환하고,
    라우터가 DocumentListItem으로 변환한다 (레이어 경계 유지).
    """

    document: Document
    category: str | None
    summary_preview: str | None

class DocumentService:
    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository,
        analysis_repository: AnalysisRepository,
    ) -> None:
        self._db = db
        self._document_repository = document_repository
        self._analysis_repository = analysis_repository

    # ------------------------------------------------------------------ 목록
    def search_documents(
        self,
        *,
        project_id: int,
        q: str | None,
        document_type: str | None,
        category: str | None,
        page: int,
        size: int,
    ) -> tuple[list[DocumentListRow], int, int]:
        documents, total = self._document_repository.search(
            project_id=project_id,
            q=q,
            document_type=document_type,
            category=category,
            page=page,
            size=size,
        )

        rows = [self._build_list_row(document) for document in documents]

        # 올림 나눗셈. total이 0이면 total_pages도 0으로 둔다.
        total_pages = (total + size - 1) // size if total else 0
        return rows, total, total_pages

    def _build_list_row(self, document: Document) -> DocumentListRow:
        category = None
        latest_category = self._analysis_repository.get_latest_by_type(
            document.id, AnalyzerType.CATEGORY.value
        )
        if latest_category is not None:
            category = latest_category.result_json.get("category")

        summary_preview = None
        latest_summary = self._analysis_repository.get_latest_by_type(
            document.id, AnalyzerType.SUMMARY.value
        )
        if latest_summary is not None:
            summary = latest_summary.result_json.get("summary")
            if summary:
                summary_preview = summary[:SUMMARY_PREVIEW_LENGTH]

        return DocumentListRow(
            document=document,
            category=category,
            summary_preview=summary_preview,
        )

    # ------------------------------------------------------------------ 상세
    def get_document(self, project_id: int, document_id: int) -> Document:
        document = self._document_repository.get_by_id(project_id, document_id)
        if document is None:
            raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
        return document

    def list_ocr_revisions(self, project_id: int, document_id: int):
        self.get_document(project_id, document_id)
        return self._document_repository.list_ocr_revisions(project_id, document_id)

    def get_review_page(self, project_id: int, document_id: int, page_id: int):
        page = self._document_repository.get_review_page(project_id, document_id, page_id)
        if page is None:
            raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
        return page

    def update_ocr_element(self, project_id: int, document_id: int, element_id: int, text: str, version: int, user_id: int):
        element = self._document_repository.get_ocr_element(project_id, document_id, element_id)
        if element is None:
            raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
        if element.version != version:
            raise BusinessError(ErrorCode.OCR_EDIT_CONFLICT)
        document = element.page.document
        before = element.text
        with transactional(self._db):
            self._db.add(OcrElementRevision(element_id=element.id, changed_by=user_id, before_text=before, after_text=text, from_version=version, to_version=version + 1))
            element.text = text
            element.version += 1
            if document.extracted_text:
                document.extracted_text.content = document.extracted_text.content.replace(before, text, 1)
                document.extracted_text.char_count = len(document.extracted_text.content)
                document.extracted_text.text_version += 1
            document.ocr_revision += 1
            if document.review_status in {ReviewStatus.PENDING.value, ReviewStatus.COMPLETED.value}:
                document.review_status = ReviewStatus.IN_PROGRESS.value
                document.reviewed_by = None
                document.reviewed_at = None
                if document.extracted_text:
                    document.extracted_text.is_confirmed = False
                    document.extracted_text.confirmed_by = None
                    document.extracted_text.confirmed_at = None
        return element

    def complete_ocr_review(self, project_id: int, document_id: int, user_id: int) -> Document:
        document = self.get_document(project_id, document_id)
        with transactional(self._db):
            document.review_status = ReviewStatus.COMPLETED.value
            document.reviewed_by = user_id
            document.reviewed_at = datetime.now().astimezone()
            if document.extracted_text:
                document.extracted_text.is_confirmed = True
                document.extracted_text.confirmed_by = user_id
                document.extracted_text.confirmed_at = document.reviewed_at
        return document

    # -------------------------------------------------------------- 다운로드
    def build_summary_text(self, project_id: int, document_id: int) -> tuple[str, str]:
        """(다운로드 파일명, 파일 내용) 을 반환한다.

        지시서 ⑧ "요약 내용 .txt 다운로드" 에 해당한다. 원문 전체가 아니라
        요약 · 카테고리 · 분류 근거만 담아 보고서 형태로 만든다.
        """
        document = self.get_document(project_id, document_id)

        latest_summary = self._analysis_repository.get_latest_by_type(
            document.id, AnalyzerType.SUMMARY.value
        )
        latest_category = self._analysis_repository.get_latest_by_type(
            document.id, AnalyzerType.CATEGORY.value
        )

        # 분석이 아직 실행되지 않았다면 다운로드할 요약이 없다.
        if latest_summary is None and latest_category is None:
            raise BusinessError(
                ErrorCode.NOT_EXTRACTED_YET,
                detail="아직 분석이 실행되지 않아 다운로드할 요약이 없습니다.",
            )

        summary = (latest_summary.result_json.get("summary") if latest_summary else None) or "-"
        category = (latest_category.result_json.get("category") if latest_category else None) or "-"
        reason = (latest_category.result_json.get("reason") if latest_category else None) or "-"

        analyzed_at = latest_summary.created_at if latest_summary else latest_category.created_at

        lines = [
            "=" * 46,
            "문서 요약 보고서",
            "=" * 46,
            f"파일명      : {document.filename}",
            f"문서 유형   : {document.document_type}",
            f"업로드 일시 : {self._format_datetime(document.created_at)}",
            f"분석 일시   : {self._format_datetime(analyzed_at)}",
            "-" * 46,
            "[카테고리]",
            category,
            f"(분류 근거: {reason})",
            "",
            "[요약]",
            summary,
            "-" * 46,
            "생성: PDF Brief AI",
        ]
        content = "\n".join(lines)

        # 확장자를 떼고 _요약.txt 를 붙인다. (보고서.pdf -> 보고서_요약.txt)
        base_name = document.filename.rsplit(".", 1)[0] if "." in document.filename else document.filename
        download_filename = f"{base_name}_요약.txt"

        return download_filename, content
    
    # ------------------------------------------------------------------ 삭제
    def delete_document(self, project_id: int, document_id: int) -> None:
        """문서와 연관 데이터, 업로드된 원본 파일을 함께 제거한다.

        extracted_texts / analyses 는 모델의 cascade 설정으로 함께 삭제된다.
        파일은 DB 삭제가 커밋된 뒤에 지운다 — 파일을 먼저 지우면 DB 삭제가
        실패했을 때 "기록은 있는데 파일이 없는" 상태가 되어 더 나쁘다.
        """
        document = self.get_document(project_id, document_id)
        stored_path = document.stored_path
        review_paths = [page.image_path for page in document.review_pages]

        with transactional(self._db):
            self._document_repository.delete(document)

        if stored_path and os.path.exists(stored_path):
            try:
                os.remove(stored_path)
            except OSError:
                # 파일 정리 실패는 조회·목록에 영향이 없으므로 요청을 실패시키지 않는다.
                logger.warning("업로드 파일 삭제 실패: %s", stored_path)

        for review_path in review_paths:
            if review_path and os.path.exists(review_path):
                try:
                    os.remove(review_path)
                except OSError:
                    logger.warning("OCR 검수 이미지 삭제 실패: %s", review_path)


    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "-"
        return value.strftime("%Y-%m-%d %H:%M:%S")

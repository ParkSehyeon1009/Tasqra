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
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from PIL import Image

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.document import Analysis, Document, OcrElement, OcrElementRevision, OcrMergeOperation
from app.models.enums import AnalyzerType, ReviewStatus
from app.extractors.ocr_extractor import OcrExtractor
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


@dataclass(frozen=True)
class OcrElementBatchChange:
    id: int
    version: int
    text: str | None = None
    is_excluded: bool | None = None
    is_paragraph_start: bool | None = None
    element_type: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    re_ocr_confidence: float | None = None
    re_ocr_applied: bool | None = None

class DocumentService:
    def __init__(
        self,
        db: Session,
        document_repository: DocumentRepository,
        analysis_repository: AnalysisRepository,
        ocr_extractor: OcrExtractor | None = None,
    ) -> None:
        self._db = db
        self._document_repository = document_repository
        self._analysis_repository = analysis_repository
        self._ocr_extractor = ocr_extractor

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

        analyses = self._analysis_repository.get_latest_by_types(
            [document.id for document in documents],
            [AnalyzerType.CATEGORY.value, AnalyzerType.SUMMARY.value],
        )
        rows = [self._build_list_row(document, analyses) for document in documents]

        # 올림 나눗셈. total이 0이면 total_pages도 0으로 둔다.
        total_pages = (total + size - 1) // size if total else 0
        return rows, total, total_pages

    def _build_list_row(
        self,
        document: Document,
        analyses: dict[tuple[int, str], Analysis],
    ) -> DocumentListRow:
        category = None
        latest_category = analyses.get(
            (document.id, AnalyzerType.CATEGORY.value)
        )
        if latest_category is not None:
            category = latest_category.result_json.get("category")

        summary_preview = None
        latest_summary = analyses.get(
            (document.id, AnalyzerType.SUMMARY.value)
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

    def get_document_for_review(self, project_id: int, document_id: int) -> Document:
        document = self._document_repository.get_by_id_with_review(
            project_id, document_id
        )
        if document is None:
            raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
        return document

    def get_latest_undoable_merge(self, project_id: int, document_id: int) -> tuple[int, int] | None:
        row = (
            self._db.query(OcrMergeOperation.id, OcrElement.page_id)
            .join(OcrElement, OcrElement.id == OcrMergeOperation.survivor_id)
            .join(Document, Document.id == OcrMergeOperation.document_id)
            .filter(Document.project_id == project_id, Document.id == document_id, OcrMergeOperation.undone_at.is_(None))
            .order_by(OcrMergeOperation.created_at.desc(), OcrMergeOperation.id.desc())
            .first()
        )
        return (row[0], row[1]) if row else None

    def list_ocr_revisions(self, project_id: int, document_id: int):
        self.get_document(project_id, document_id)
        return self._document_repository.list_ocr_revisions(project_id, document_id)

    def get_review_page(self, project_id: int, document_id: int, page_id: int):
        page = self._document_repository.get_review_page(project_id, document_id, page_id)
        if page is None:
            raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
        return page

    @staticmethod
    def _ordered_ocr_elements(document: Document) -> list[OcrElement]:
        return [
            element
            for page in document.review_pages
            for element in page.elements
            if not element.is_deleted
        ]

    def _replace_ocr_content(self, document: Document, element: OcrElement, replacement: str) -> bool:
        extracted = document.extracted_text
        if extracted is None:
            return False
        if element.content_start is None or element.content_end is None:
            raise BusinessError(ErrorCode.OCR_CONTENT_MAPPING_CONFLICT)

        start = element.content_start
        end = element.content_end
        expected = element.text if element.is_in_content else ""
        if start > end or end > len(extracted.content) or extracted.content[start:end] != expected:
            raise BusinessError(ErrorCode.OCR_CONTENT_MAPPING_CONFLICT)
        if expected == replacement:
            return False

        ordered = self._ordered_ocr_elements(document)
        current_order = next(index for index, item in enumerate(ordered) if item.id == element.id)
        delta = len(replacement) - (end - start)
        extracted.content = extracted.content[:start] + replacement + extracted.content[end:]
        element.content_end = start + len(replacement)

        for candidate_order, candidate in enumerate(ordered):
            if candidate.id == element.id or candidate.content_start is None or candidate.content_end is None:
                continue
            follows_range = candidate.content_start > end or (candidate.content_start == end and candidate_order > current_order)
            if follows_range:
                candidate.content_start += delta
                candidate.content_end += delta

        extracted.char_count = len(extracted.content)
        return True

    def _replace_ocr_contents(self, document: Document, replacements: list[tuple[OcrElement, str]]) -> bool:
        extracted = document.extracted_text
        if extracted is None or not replacements:
            return False

        ordered = self._ordered_ocr_elements(document)
        order_by_id = {element.id: index for index, element in enumerate(ordered)}
        original_ranges = {element.id: (element.content_start, element.content_end) for element in ordered}
        prepared: list[tuple[OcrElement, int, int, str, int, int]] = []
        for element, replacement in replacements:
            start = element.content_start
            end = element.content_end
            if start is None or end is None:
                raise BusinessError(ErrorCode.OCR_CONTENT_MAPPING_CONFLICT)
            if start > end or end > len(extracted.content) or extracted.content[start:end] != element.text:
                raise BusinessError(ErrorCode.OCR_CONTENT_MAPPING_CONFLICT)
            if replacement == element.text:
                continue
            prepared.append((element, start, end, replacement, len(replacement) - (end - start), order_by_id[element.id]))

        if not prepared:
            return False

        content = extracted.content
        for _, start, end, replacement, _, _ in sorted(prepared, key=lambda item: (item[1], item[5]), reverse=True):
            content = content[:start] + replacement + content[end:]
        extracted.content = content

        replacement_by_id = {item[0].id: item for item in prepared}
        for candidate_order, candidate in enumerate(ordered):
            original_start, original_end = original_ranges[candidate.id]
            if original_start is None or original_end is None:
                continue
            shift = sum(
                delta
                for _, _, replacement_end, _, delta, replacement_order in prepared
                if original_start > replacement_end
                or (original_start == replacement_end and candidate_order > replacement_order)
            )
            candidate.content_start = original_start + shift
            own_replacement = replacement_by_id.get(candidate.id)
            candidate.content_end = (
                candidate.content_start + len(own_replacement[3])
                if own_replacement is not None
                else original_end + shift
            )

        extracted.char_count = len(extracted.content)
        return True

    @staticmethod
    def _mark_review_in_progress(document: Document) -> None:
        if document.review_status not in {ReviewStatus.PENDING.value, ReviewStatus.COMPLETED.value}:
            return
        document.review_status = ReviewStatus.IN_PROGRESS.value
        document.reviewed_by = None
        document.reviewed_at = None
        if document.extracted_text:
            document.extracted_text.is_confirmed = False
            document.extracted_text.confirmed_by = None
            document.extracted_text.confirmed_at = None

    def update_ocr_elements_batch(
        self,
        project_id: int,
        document_id: int,
        changes: list[OcrElementBatchChange],
        user_id: int,
    ) -> tuple[Document, list[OcrElement]]:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(
                project_id, document_id
            )
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)

            ids = [change.id for change in changes]
            elements = self._document_repository.get_ocr_elements_for_update(project_id, document_id, ids)
            elements_by_id = {element.id: element for element in elements}
            if len(elements_by_id) != len(ids):
                raise BusinessError(ErrorCode.OCR_ELEMENT_NOT_FOUND)

            for change in changes:
                if elements_by_id[change.id].version != change.version:
                    raise BusinessError(ErrorCode.OCR_EDIT_CONFLICT)

            paragraph_updates: dict[int, bool | None] = {}
            for change in changes:
                element = elements_by_id[change.id]
                resulting_type = change.element_type or element.element_type
                requested_paragraph_start = change.is_paragraph_start
                if resulting_type == "HEADING":
                    requested_paragraph_start = True
                elif resulting_type in {"TABLE_ROW", "TABLE_HEADER"}:
                    if requested_paragraph_start is True:
                        raise BusinessError(ErrorCode.OCR_INVALID_STRUCTURE)
                    requested_paragraph_start = False
                paragraph_updates[change.id] = requested_paragraph_start
                resulting_x = element.x if change.x is None else change.x
                resulting_y = element.y if change.y is None else change.y
                resulting_width = element.width if change.width is None else change.width
                resulting_height = element.height if change.height is None else change.height
                if resulting_width <= 0 or resulting_height <= 0 or resulting_x + resulting_width > 1 or resulting_y + resulting_height > 1:
                    raise BusinessError(ErrorCode.OCR_INVALID_STRUCTURE)

            text_replacements = [
                (elements_by_id[change.id], change.text)
                for change in changes
                if change.text is not None
                and change.text != elements_by_id[change.id].text
                and elements_by_id[change.id].is_in_content
            ]
            content_changed = self._replace_ocr_contents(document, text_replacements)
            chunk_structure_changed = False
            any_changed = False

            for change in changes:
                element = elements_by_id[change.id]
                before_text = element.text
                item_changed = False

                if change.text is not None and change.text != element.text:
                    self._db.add(OcrElementRevision(
                        element_id=element.id,
                        changed_by=user_id,
                        before_text=before_text,
                        after_text=change.text,
                        from_version=change.version,
                        to_version=change.version + 1,
                    ))
                    element.text = change.text
                    item_changed = True

                if change.is_excluded is not None and change.is_excluded != element.is_excluded:
                    element.is_excluded = change.is_excluded
                    item_changed = True

                if change.element_type is not None and change.element_type != element.element_type:
                    element.element_type = change.element_type
                    element.element_type_source = "USER_CORRECTED"
                    chunk_structure_changed = True
                    item_changed = True

                requested_paragraph_start = paragraph_updates[change.id]

                if requested_paragraph_start is not None and requested_paragraph_start != element.is_paragraph_start:
                    element.is_paragraph_start = requested_paragraph_start
                    chunk_structure_changed = True
                    item_changed = True

                for field in ("x", "y", "width", "height"):
                    requested_value = getattr(change, field)
                    if requested_value is not None and requested_value != getattr(element, field):
                        setattr(element, field, requested_value)
                        item_changed = True

                if change.re_ocr_applied:
                    element.confidence = change.re_ocr_confidence
                    element.source = "RE_OCR"
                    item_changed = True

                if item_changed:
                    element.version += 1
                    any_changed = True

            if any_changed:
                document.ocr_revision += 1
                if document.extracted_text:
                    if content_changed or chunk_structure_changed:
                        document.extracted_text.text_version += 1
                    document.extracted_text.ocr_char_count = sum(
                        len(element.text)
                        for element in self._ordered_ocr_elements(document)
                        if not element.is_excluded
                    )
                self._mark_review_in_progress(document)

        return document, [elements_by_id[change.id] for change in changes]

    def update_ocr_element(self, project_id: int, document_id: int, element_id: int, text: str, version: int, user_id: int):
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(
                project_id, document_id
            )
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            element = self._document_repository.get_ocr_element_for_update(project_id, document_id, element_id)
            if element is None:
                raise BusinessError(ErrorCode.OCR_ELEMENT_NOT_FOUND)
            if element.version != version:
                raise BusinessError(ErrorCode.OCR_EDIT_CONFLICT)
            before = element.text
            content_changed = element.is_in_content and self._replace_ocr_content(document, element, text)
            self._db.add(OcrElementRevision(element_id=element.id, changed_by=user_id, before_text=before, after_text=text, from_version=version, to_version=version + 1))
            element.text = text
            element.version += 1
            if document.extracted_text:
                if content_changed:
                    document.extracted_text.text_version += 1
                if element.is_in_content:
                    document.extracted_text.ocr_char_count = max(document.extracted_text.ocr_char_count + len(text) - len(before), 0)
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

    def set_ocr_element_exclusion(self, project_id: int, document_id: int, element_id: int, is_excluded: bool, version: int):
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            element = self._document_repository.get_ocr_element_for_update(project_id, document_id, element_id)
            if element is None:
                raise BusinessError(ErrorCode.OCR_ELEMENT_NOT_FOUND)
            if element.version != version:
                raise BusinessError(ErrorCode.OCR_EDIT_CONFLICT)
            element.is_excluded = is_excluded
            element.version += 1
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

    def reprocess_ocr_element(self, project_id: int, document_id: int, element_id: int, x: float, y: float, width: float, height: float) -> tuple[OcrElement, str, float | None]:
        element = self._document_repository.get_ocr_element(project_id, document_id, element_id)
        if element is None:
            raise BusinessError(ErrorCode.OCR_ELEMENT_NOT_FOUND)
        if element.is_deleted:
            raise BusinessError(ErrorCode.OCR_ELEMENT_DELETED)
        if self._ocr_extractor is None:
            raise BusinessError(ErrorCode.RE_OCR_FAILED)
        page = self._document_repository.get_review_page(project_id, document_id, element.page_id)
        if page is None:
            raise BusinessError(ErrorCode.PAGE_NOT_FOUND)
        try:
            with Image.open(page.image_path) as source:
                image = source.convert("RGB")
                left = max(0, min(image.width - 1, round(x * image.width)))
                top = max(0, min(image.height - 1, round(y * image.height)))
                right = max(left + 1, min(image.width, round((x + width) * image.width)))
                bottom = max(top + 1, min(image.height, round((y + height) * image.height)))
                results = self._ocr_extractor.extract(image.crop((left, top, right, bottom)), normalize_orientation=False)
        except BusinessError:
            raise
        except Exception as exc:
            raise BusinessError(ErrorCode.RE_OCR_FAILED) from exc
        recognized_text = "\n".join(item.content for item in results if item.content.strip())
        if not recognized_text:
            raise BusinessError(ErrorCode.RE_OCR_FAILED)
        scores = [item.confidence for item in results if item.confidence is not None]
        confidence = sum(scores) / len(scores) if scores else None
        return element, recognized_text, confidence

    def merge_ocr_elements(self, project_id: int, document_id: int, items: list[tuple[int, int]], user_id: int) -> tuple[Document, OcrElement, list[int], OcrMergeOperation]:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            ids = [item[0] for item in items]
            elements = self._document_repository.get_ocr_elements_for_update(project_id, document_id, ids)
            if len(elements) != len(ids) or any(element.is_deleted for element in elements):
                raise BusinessError(ErrorCode.OCR_ELEMENT_NOT_FOUND)
            if any(element.is_excluded or not element.is_in_content for element in elements):
                raise BusinessError(ErrorCode.OCR_INVALID_STRUCTURE)
            versions = dict(items)
            if any(element.version != versions[element.id] for element in elements):
                raise BusinessError(ErrorCode.OCR_EDIT_CONFLICT)
            if len({element.page_id for element in elements}) != 1:
                raise BusinessError(ErrorCode.OCR_INVALID_STRUCTURE)
            page = next(page for page in document.review_pages if page.id == elements[0].page_id)
            active = [element for element in page.elements if not element.is_deleted]
            positions = sorted(active.index(element) for element in elements)
            if positions != list(range(positions[0], positions[-1] + 1)):
                raise BusinessError(ErrorCode.OCR_INVALID_STRUCTURE)
            ordered = sorted(elements, key=lambda element: element.reading_order)
            for first, second in zip(ordered, ordered[1:]):
                horizontal_overlap = max(0.0, min(first.x + first.width, second.x + second.width) - max(first.x, second.x))
                vertical_overlap = max(0.0, min(first.y + first.height, second.y + second.height) - max(first.y, second.y))
                same_column = horizontal_overlap / max(min(first.width, second.width), 0.001) >= 0.35
                same_line = vertical_overlap / max(min(first.height, second.height), 0.001) >= 0.5
                vertical_gap = max(0.0, max(first.y, second.y) - min(first.y + first.height, second.y + second.height))
                horizontal_gap = max(0.0, max(first.x, second.x) - min(first.x + first.width, second.x + second.width))
                if not ((same_column and vertical_gap <= max(first.height, second.height) * 3) or (same_line and horizontal_gap <= max(first.height, second.height) * 3)):
                    raise BusinessError(ErrorCode.OCR_MERGE_TOO_FAR)
            survivor, removed = ordered[0], ordered[1:]
            snapshot = {
                "selected_ids": ids,
                "extracted_text": ({
                    "content": document.extracted_text.content,
                    "char_count": document.extracted_text.char_count,
                    "ocr_char_count": document.extracted_text.ocr_char_count,
                    "text_version": document.extracted_text.text_version,
                    "is_confirmed": document.extracted_text.is_confirmed,
                    "confirmed_by": document.extracted_text.confirmed_by,
                    "confirmed_at": document.extracted_text.confirmed_at.isoformat() if document.extracted_text.confirmed_at else None,
                } if document.extracted_text else None),
                "elements": [{
                    "id": element.id, "text": element.text, "x": element.x, "y": element.y,
                    "width": element.width, "height": element.height, "confidence": element.confidence,
                    "source": element.source, "is_deleted": element.is_deleted, "is_excluded": element.is_excluded,
                    "is_in_content": element.is_in_content, "content_start": element.content_start,
                    "content_end": element.content_end, "version": element.version,
                } for element in page.elements],
            }
            merged_text = "\n".join(element.text for element in ordered if element.text)
            content_changed = self._replace_ocr_contents(document, [(survivor, merged_text), *[(element, "") for element in removed if element.is_in_content]])
            self._db.add(OcrElementRevision(element_id=survivor.id, changed_by=user_id, before_text=survivor.text, after_text=merged_text, from_version=survivor.version, to_version=survivor.version + 1))
            survivor.text = merged_text
            left = min(element.x for element in ordered)
            top = min(element.y for element in ordered)
            right = max(element.x + element.width for element in ordered)
            bottom = max(element.y + element.height for element in ordered)
            survivor.x, survivor.y, survivor.width, survivor.height = left, top, right - left, bottom - top
            survivor.confidence = min((element.confidence for element in ordered if element.confidence is not None), default=None)
            survivor.version += 1
            operation = OcrMergeOperation(document_id=document.id, survivor_id=survivor.id, created_by=user_id, snapshot_json=snapshot, merged_version=survivor.version)
            self._db.add(operation)
            for element in removed:
                self._db.add(OcrElementRevision(element_id=element.id, changed_by=user_id, before_text=element.text, after_text="", from_version=element.version, to_version=element.version + 1))
                element.is_deleted = True
                element.is_in_content = False
                element.version += 1
            document.ocr_revision += 1
            if document.extracted_text:
                if content_changed:
                    document.extracted_text.text_version += 1
                document.extracted_text.ocr_char_count = sum(len(element.text) for element in self._ordered_ocr_elements(document) if not element.is_excluded)
            self._mark_review_in_progress(document)
        return document, survivor, [element.id for element in removed], operation

    def undo_ocr_merge(self, project_id: int, document_id: int, operation_id: int, user_id: int) -> tuple[Document, list[OcrElement]]:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            operation = self._db.query(OcrMergeOperation).filter(
                OcrMergeOperation.id == operation_id,
                OcrMergeOperation.document_id == document_id,
            ).with_for_update().one_or_none()
            if operation is None or operation.undone_at is not None:
                raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            all_elements = {element.id: element for page in document.review_pages for element in page.elements}
            survivor = all_elements.get(operation.survivor_id)
            if survivor is None or survivor.version != operation.merged_version:
                raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            selected_ids = set(operation.snapshot_json["selected_ids"])
            for saved in operation.snapshot_json["elements"]:
                element = all_elements.get(saved["id"])
                expected_version = saved["version"] + (1 if saved["id"] in selected_ids else 0)
                if element is None or element.version != expected_version:
                    raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            saved_text = operation.snapshot_json.get("extracted_text")
            if saved_text and document.extracted_text and document.extracted_text.text_version != saved_text["text_version"] + 1:
                raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            restored = []
            for saved in operation.snapshot_json["elements"]:
                element = all_elements.get(saved["id"])
                current_version = element.version
                for field in ("text", "x", "y", "width", "height", "confidence", "source", "is_deleted", "is_excluded", "is_in_content", "content_start", "content_end"):
                    setattr(element, field, saved[field])
                element.version = current_version + 1
                restored.append(element)
            if saved_text and document.extracted_text:
                for field in ("content", "char_count", "ocr_char_count", "is_confirmed", "confirmed_by"):
                    setattr(document.extracted_text, field, saved_text[field])
                document.extracted_text.text_version += 1
                document.extracted_text.confirmed_at = datetime.fromisoformat(saved_text["confirmed_at"]) if saved_text["confirmed_at"] else None
            operation.undone_at = datetime.now(timezone.utc)
            document.ocr_revision += 1
            self._mark_review_in_progress(document)
        return document, restored

    def create_ocr_element(self, project_id: int, document_id: int, page_id: int, text: str, x: float, y: float, width: float, height: float) -> OcrElement:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            page = next((item for item in document.review_pages if item.id == page_id), None)
            if page is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            reading_order = max((item.reading_order for item in page.elements), default=-1) + 1
            content_start = content_end = None
            is_in_content = False
            if document.extracted_text is not None:
                separator = "\n" if document.extracted_text.content else ""
                content_start = len(document.extracted_text.content) + len(separator)
                document.extracted_text.content += separator + text
                content_end = content_start + len(text)
                document.extracted_text.char_count = len(document.extracted_text.content)
                document.extracted_text.ocr_char_count += len(text)
                document.extracted_text.text_version += 1
                is_in_content = True
            element = self._document_repository.create_ocr_element(OcrElement(
                page_id=page.id, original_text=text, text=text, x=x, y=y, width=width, height=height,
                confidence=None, source="USER", element_type="TEXT_LINE", element_type_source="USER",
                is_paragraph_start=False, reading_order=reading_order, version=1, is_deleted=False,
                is_excluded=False, content_start=content_start, content_end=content_end, is_in_content=is_in_content,
            ))
            page.elements.append(element)
            document.ocr_revision += 1
            self._mark_review_in_progress(document)
        return element

    def set_ocr_element_deletion(self, project_id: int, document_id: int, element_id: int, is_deleted: bool, version: int) -> OcrElement:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            element = self._document_repository.get_ocr_element_for_update(project_id, document_id, element_id)
            if element is None:
                raise BusinessError(ErrorCode.OCR_ELEMENT_NOT_FOUND)
            if element.version != version:
                raise BusinessError(ErrorCode.OCR_EDIT_CONFLICT)
            if element.is_deleted == is_deleted:
                return element
            content_changed = False
            if is_deleted:
                if element.is_in_content:
                    content_changed = self._replace_ocr_content(document, element, "")
                    element.is_in_content = False
                element.is_deleted = True
            else:
                element.is_deleted = False
                if not element.is_excluded and not element.is_in_content:
                    content_changed = self._replace_ocr_content(document, element, element.text)
                    element.is_in_content = True
            element.version += 1
            document.ocr_revision += 1
            if document.extracted_text:
                if content_changed:
                    document.extracted_text.text_version += 1
                document.extracted_text.ocr_char_count = sum(len(item.text) for item in self._ordered_ocr_elements(document) if not item.is_excluded)
            self._mark_review_in_progress(document)
        return element

    def complete_ocr_review(self, project_id: int, document_id: int, user_id: int) -> Document:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(
                project_id, document_id
            )
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            if document.extracted_text:
                content_changed = False
                for element in self._ordered_ocr_elements(document):
                    if element.is_excluded and element.is_in_content:
                        content_changed = self._replace_ocr_content(document, element, "") or content_changed
                        element.is_in_content = False
                    elif not element.is_excluded and not element.is_in_content:
                        content_changed = self._replace_ocr_content(document, element, element.text) or content_changed
                        element.is_in_content = True
                if content_changed:
                    document.extracted_text.text_version += 1
                document.extracted_text.ocr_char_count = sum(
                    len(element.text)
                    for element in self._ordered_ocr_elements(document)
                    if not element.is_excluded
                )
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

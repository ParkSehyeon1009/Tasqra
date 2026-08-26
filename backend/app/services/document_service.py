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
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from PIL import Image

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.extractors.layout import LayoutElement
from app.models.document import Analysis, Document, OcrElement, OcrElementRevision, OcrMergeOperation, OcrStructureEvent
from app.models.enums import AnalyzerType, ReviewStatus
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.reading_order import build_reading_groups
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
        document_state: str | None,
        category: str | None,
        page: int,
        size: int,
    ) -> tuple[list[DocumentListRow], int, int]:
        documents, total = self._document_repository.search(
            project_id=project_id,
            q=q,
            document_type=document_type,
            document_state=document_state,
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
            .filter(Document.project_id == project_id, Document.id == document_id, OcrMergeOperation.undone_at.is_(None), OcrElement.is_deleted.is_(False), OcrElement.version == OcrMergeOperation.merged_version)
            .order_by(OcrMergeOperation.created_at.desc(), OcrMergeOperation.id.desc())
            .first()
        )
        return (row[0], row[1]) if row else None

    def list_undoable_merges(self, project_id: int, document_id: int) -> list[tuple[int, int, int, int]]:
        return [
            (row[0], row[1], row[2], len(row[3].get("selected_ids", [])))
            for row in (
                self._db.query(OcrMergeOperation.id, OcrMergeOperation.survivor_id, OcrElement.page_id, OcrMergeOperation.snapshot_json)
                .join(OcrElement, OcrElement.id == OcrMergeOperation.survivor_id)
                .join(Document, Document.id == OcrMergeOperation.document_id)
                .filter(
                    Document.project_id == project_id,
                    Document.id == document_id,
                    OcrMergeOperation.undone_at.is_(None),
                    OcrElement.is_deleted.is_(False),
                    OcrElement.version == OcrMergeOperation.merged_version,
                )
                .order_by(OcrMergeOperation.created_at.desc(), OcrMergeOperation.id.desc())
                .all()
            )
        ]

    def list_ocr_structure_events(self, project_id: int, document_id: int) -> list[OcrStructureEvent]:
        return self._db.query(OcrStructureEvent).join(Document, Document.id == OcrStructureEvent.document_id).filter(Document.project_id == project_id, Document.id == document_id, OcrStructureEvent.event_type.in_(("MERGE", "UNMERGE"))).order_by(OcrStructureEvent.created_at.desc(), OcrStructureEvent.id.desc()).limit(50).all()

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
    def _coordinate_order(elements: list[OcrElement]) -> list[OcrElement]:
        """2단은 단별로, 표는 하나의 영역으로 보고 읽는 순서를 계산한다."""
        table_groups: dict[tuple[str, int], list[OcrElement]] = {}
        regular: list[OcrElement] = []
        for element in elements:
            if element.element_type in {"TABLE_ROW", "TABLE_HEADER"}:
                key = ("table", element.table_id if element.table_id is not None else element.id)
                table_groups.setdefault(key, []).append(element)
            else:
                regular.append(element)

        layout_to_elements: dict[int, list[OcrElement]] = {}
        regular_layouts: list[LayoutElement] = []
        for element in regular:
            layout = LayoutElement(
                x=element.x * 1000, y=element.y * 1000,
                x2=(element.x + element.width) * 1000,
                y2=(element.y + element.height) * 1000,
                content=element.text, source="ocr",
            )
            regular_layouts.append(layout)
            layout_to_elements[id(layout)] = [element]

        atomic_layouts: list[LayoutElement] = []
        for grouped_elements in table_groups.values():
            layout = LayoutElement(
                x=min(item.x for item in grouped_elements) * 1000,
                y=min(item.y for item in grouped_elements) * 1000,
                x2=max(item.x + item.width for item in grouped_elements) * 1000,
                y2=max(item.y + item.height for item in grouped_elements) * 1000,
                content="\n".join(item.text for item in grouped_elements),
                source="ocr",
            )
            atomic_layouts.append(layout)
            layout_to_elements[id(layout)] = sorted(
                grouped_elements,
                key=lambda item: (item.table_row if item.table_row is not None else 10**9, item.y, item.x, item.id or 0),
            )

        groups = build_reading_groups(regular_layouts, atomic_layouts, page_width=1000.0)
        if groups is not None:
            return [
                element
                for group in groups
                for layout in group.elements
                for element in layout_to_elements[id(layout)]
            ]

        # 박스가 적거나 단 분리가 불확실하면 기본 행 정렬을 사용한다.
        lines: list[list[OcrElement]] = []
        for element in sorted(elements, key=lambda item: (item.y, item.x, item.id or 0)):
            element_bottom = element.y + element.height
            matching = next((
                line for line in lines
                if max(0.0, min(element_bottom, max(item.y + item.height for item in line)) - max(element.y, min(item.y for item in line)))
                / max(min(element.height, max(item.y + item.height for item in line) - min(item.y for item in line)), 1e-9) >= 0.45
            ), None)
            if matching is None:
                lines.append([element])
            else:
                matching.append(element)
        lines.sort(key=lambda line: min(item.y for item in line))
        return [item for line in lines for item in sorted(line, key=lambda value: (value.x, value.y, value.id or 0))]

    def _insert_page_ocr_content(self, document: Document, page, element: OcrElement) -> bool:
        extracted = document.extracted_text
        if extracted is None:
            return False
        page_mapped = [
            item for item in page.elements
            if item.id != element.id and not item.is_deleted and item.is_in_content
            and item.content_start is not None and item.content_end is not None
        ]
        if page_mapped:
            insertion_at = max(item.content_end for item in page_mapped)
            inserted = "\n" + element.text
            element.content_start = insertion_at + 1
        else:
            later = [
                item for candidate_page in document.review_pages if candidate_page.page_number > page.page_number
                for item in candidate_page.elements
                if not item.is_deleted and item.is_in_content and item.content_start is not None
            ]
            if later:
                insertion_at = min(item.content_start for item in later)
                inserted = element.text + "\n"
                element.content_start = insertion_at
            else:
                separator = "\n" if extracted.content else ""
                insertion_at = len(extracted.content)
                inserted = separator + element.text
                element.content_start = insertion_at + len(separator)
        extracted.content = extracted.content[:insertion_at] + inserted + extracted.content[insertion_at:]
        element.content_end = element.content_start + len(element.text)
        element.is_in_content = True
        for candidate in (item for candidate_page in document.review_pages for item in candidate_page.elements):
            if candidate.id == element.id or candidate.content_start is None or candidate.content_end is None:
                continue
            if candidate.content_start >= insertion_at:
                candidate.content_start += len(inserted)
                candidate.content_end += len(inserted)
        extracted.char_count = len(extracted.content)
        return True

    def _reorder_page_ocr_content(self, document: Document, page) -> bool:
        ordered = self._coordinate_order(list(page.elements))
        order_changed = any(item.reading_order != index for index, item in enumerate(ordered))
        for index, item in enumerate(ordered):
            item.reading_order = index

        desired = [
            item for item in ordered
            if not item.is_deleted and item.is_in_content
            and item.content_start is not None and item.content_end is not None
        ]
        slots = sorted(desired, key=lambda item: (item.content_start, item.content_end, item.id or 0))
        if not desired or [item.id for item in desired] == [item.id for item in slots]:
            return order_changed

        extracted = document.extracted_text
        if extracted is None:
            return order_changed
        for item in slots:
            if extracted.content[item.content_start:item.content_end] != item.text:
                raise BusinessError(ErrorCode.OCR_CONTENT_MAPPING_CONFLICT)

        original_ranges = {
            item.id: (item.content_start, item.content_end)
            for candidate_page in document.review_pages for item in candidate_page.elements
            if item.content_start is not None and item.content_end is not None
        }
        replacements = [
            (slot.content_start, slot.content_end, target.text)
            for slot, target in zip(slots, desired, strict=True)
        ]
        content = extracted.content
        for start, end, replacement in reversed(replacements):
            content = content[:start] + replacement + content[end:]
        extracted.content = content

        target_ids = {item.id for item in desired}
        cumulative_shift = 0
        for (start, end, replacement), target in zip(replacements, desired, strict=True):
            target.content_start = start + cumulative_shift
            target.content_end = target.content_start + len(replacement)
            cumulative_shift += len(replacement) - (end - start)
        for candidate in (item for candidate_page in document.review_pages for item in candidate_page.elements):
            if candidate.id in target_ids or candidate.id not in original_ranges:
                continue
            original_start, original_end = original_ranges[candidate.id]
            shift = sum(len(replacement) - (end - start) for start, end, replacement in replacements if end <= original_start)
            candidate.content_start = original_start + shift
            candidate.content_end = original_end + shift
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
            geometry_changed_pages = set()

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
                        geometry_changed_pages.add(element.page_id)
                        item_changed = True

                if change.re_ocr_applied:
                    element.confidence = change.re_ocr_confidence
                    element.source = "RE_OCR"
                    item_changed = True

                if item_changed:
                    element.version += 1
                    any_changed = True

            for review_page in document.review_pages:
                if review_page.id in geometry_changed_pages:
                    content_changed = self._reorder_page_ocr_content(document, review_page) or content_changed

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

    def merge_ocr_elements(self, project_id: int, document_id: int, items: list[tuple[int, int]], user_id: int, join_with_space: bool = True, auto_commit: bool = True) -> tuple[Document, OcrElement, list[int], OcrMergeOperation]:
        context = transactional(self._db) if auto_commit else nullcontext(self._db)
        with context:
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
            first = ordered[0]
            snapshot = {
                "result_strategy": "NEW_ELEMENT",
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
            separator = " " if join_with_space else "\n"
            merged_text = separator.join(element.text for element in ordered if element.text)
            content_changed = self._replace_ocr_contents(document, [(first, merged_text), *[(element, "") for element in ordered[1:] if element.is_in_content]])
            left = min(element.x for element in ordered)
            top = min(element.y for element in ordered)
            right = max(element.x + element.width for element in ordered)
            bottom = max(element.y + element.height for element in ordered)
            merged = self._document_repository.create_ocr_element(OcrElement(
                page_id=page.id, original_text=merged_text, text=merged_text,
                x=left, y=top, width=right - left, height=bottom - top,
                confidence=min((element.confidence for element in ordered if element.confidence is not None), default=None),
                source="USER", element_type=first.element_type, element_type_source="USER_CORRECTED",
                is_paragraph_start=first.is_paragraph_start, table_id=None, table_row=None,
                reading_order=first.reading_order, version=1, is_deleted=False, is_excluded=False,
                content_start=first.content_start, content_end=first.content_end, is_in_content=True,
            ))
            page.elements.append(merged)
            operation = OcrMergeOperation(document_id=document.id, survivor_id=merged.id, created_by=user_id, snapshot_json=snapshot, merged_version=merged.version)
            self._db.add(operation)
            self._db.add(OcrStructureEvent(document_id=document.id, page_id=page.id, event_type="MERGE", details_json={"result_id": merged.id, "source_ids": ids, "source_count": len(ids)}, created_by=user_id))
            for element in ordered:
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
        return document, merged, [element.id for element in ordered], operation

    def merge_ocr_element_groups(self, project_id: int, document_id: int, groups: list[list[tuple[int, int]]], user_id: int, join_with_space: bool = True) -> list[tuple[Document, OcrElement, list[int], OcrMergeOperation]]:
        with transactional(self._db):
            results = [self.merge_ocr_elements(project_id, document_id, group, user_id, join_with_space, auto_commit=False) for group in groups]
        return results

    def undo_ocr_merge(self, project_id: int, document_id: int, operation_id: int, user_id: int, auto_commit: bool = True) -> tuple[Document, list[OcrElement], list[int]]:
        context = transactional(self._db) if auto_commit else nullcontext(self._db)
        with context:
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
            merged = all_elements.get(operation.survivor_id)
            if merged is None or merged.is_deleted or merged.version != operation.merged_version:
                raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            selected_ids = set(operation.snapshot_json["selected_ids"])
            selected_snapshots = [saved for saved in operation.snapshot_json["elements"] if saved["id"] in selected_ids]
            uses_new_element = operation.snapshot_json.get("result_strategy") == "NEW_ELEMENT"
            for saved in selected_snapshots:
                element = all_elements.get(saved["id"])
                may_be_legacy_survivor = not uses_new_element and element is not None and element.id == merged.id
                if element is None or (not element.is_deleted and not may_be_legacy_survivor):
                    raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            saved_text = operation.snapshot_json.get("extracted_text")
            content_changed = False
            range_origin = None
            restored_content_start = None
            if saved_text and document.extracted_text:
                content_snapshots = [saved for saved in selected_snapshots if saved["is_in_content"] and saved["content_start"] is not None and saved["content_end"] is not None]
                if content_snapshots:
                    range_origin = min(saved["content_start"] for saved in content_snapshots)
                    range_end = max(saved["content_end"] for saved in content_snapshots)
                    original_segment = saved_text["content"][range_origin:range_end]
                    restored_content_start = merged.content_start
                    content_changed = self._replace_ocr_content(document, merged, original_segment)
            restored = []
            for saved in selected_snapshots:
                element = all_elements.get(saved["id"])
                current_version = element.version
                for field in ("text", "x", "y", "width", "height", "confidence", "source", "is_deleted", "is_excluded", "is_in_content"):
                    setattr(element, field, saved[field])
                if saved["content_start"] is not None and range_origin is not None and restored_content_start is not None:
                    element.content_start = restored_content_start + saved["content_start"] - range_origin
                    element.content_end = restored_content_start + saved["content_end"] - range_origin
                else:
                    element.content_start = saved["content_start"]
                    element.content_end = saved["content_end"]
                element.version = current_version + 1
                self._db.query(OcrMergeOperation).filter(OcrMergeOperation.survivor_id == element.id, OcrMergeOperation.undone_at.is_(None)).update({OcrMergeOperation.merged_version: element.version}, synchronize_session=False)
                restored.append(element)
            deleted_ids = []
            if uses_new_element:
                merged.is_deleted = True
                merged.is_in_content = False
                merged.version += 1
                deleted_ids.append(merged.id)
            if saved_text and document.extracted_text:
                if content_changed:
                    document.extracted_text.text_version += 1
                document.extracted_text.ocr_char_count = sum(len(element.text) for element in self._ordered_ocr_elements(document) if not element.is_excluded)
            if len(restored) != len(selected_snapshots) or any(
                abs(getattr(element, field) - saved[field]) > 1e-9
                for element, saved in zip(restored, selected_snapshots)
                for field in ("x", "y", "width", "height")
            ):
                raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            operation.undone_at = datetime.now(timezone.utc)
            self._db.add(OcrStructureEvent(document_id=document.id, page_id=merged.page_id, event_type="UNMERGE", details_json={"result_id": merged.id, "restored_ids": [element.id for element in restored], "restored_count": len(restored)}, created_by=user_id))
            document.ocr_revision += 1
            self._mark_review_in_progress(document)
        return document, restored, deleted_ids

    def undo_ocr_merge_to_originals(self, project_id: int, document_id: int, operation_id: int, user_id: int) -> tuple[Document, list[OcrElement], list[int]]:
        with transactional(self._db):
            pending = [operation_id]
            restored_by_id: dict[int, OcrElement] = {}
            deleted_ids: list[int] = []
            document = None
            while pending:
                current_operation_id = pending.pop()
                document, restored, deleted = self.undo_ocr_merge(project_id, document_id, current_operation_id, user_id, auto_commit=False)
                deleted_ids.extend(deleted)
                for deleted_id in deleted:
                    restored_by_id.pop(deleted_id, None)
                for element in restored:
                    restored_by_id[element.id] = element
                    nested = self._db.query(OcrMergeOperation).filter(
                        OcrMergeOperation.survivor_id == element.id,
                        OcrMergeOperation.undone_at.is_(None),
                        OcrMergeOperation.merged_version == element.version,
                    ).order_by(OcrMergeOperation.created_at.desc(), OcrMergeOperation.id.desc()).first()
                    if nested is not None:
                        pending.append(nested.id)
            if document is None:
                raise BusinessError(ErrorCode.OCR_MERGE_UNDO_UNAVAILABLE)
            final_restored = [element for element in restored_by_id.values() if not element.is_deleted]
        return document, final_restored, deleted_ids

    def create_ocr_element(self, project_id: int, document_id: int, page_id: int, text: str, x: float, y: float, width: float, height: float) -> OcrElement:
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update_with_review(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            page = next((item for item in document.review_pages if item.id == page_id), None)
            if page is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            element = self._document_repository.create_ocr_element(OcrElement(
                page_id=page.id, original_text=text, text=text, x=x, y=y, width=width, height=height,
                confidence=None, source="USER", element_type="TEXT_LINE", element_type_source="USER",
                is_paragraph_start=False, reading_order=len(page.elements), version=1, is_deleted=False,
                is_excluded=False, content_start=None, content_end=None, is_in_content=False,
            ))
            page.elements.append(element)
            if document.extracted_text is not None:
                self._insert_page_ocr_content(document, page, element)
                self._reorder_page_ocr_content(document, page)
                document.extracted_text.ocr_char_count += len(text)
                document.extracted_text.text_version += 1
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

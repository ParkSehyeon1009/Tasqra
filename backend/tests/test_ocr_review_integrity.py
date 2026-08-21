from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.models.enums import ReviewStatus
from app.services.document_service import DocumentService, OcrElementBatchChange


def build_service(*, document=None, element=None):
    db = MagicMock()
    repository = MagicMock()
    repository.get_by_id_for_update.return_value = document
    repository.get_by_id_for_update_with_review.return_value = document
    repository.get_ocr_element_for_update.return_value = element
    service = DocumentService(db, repository, MagicMock())
    return service, db, repository


def editable_document():
    return SimpleNamespace(
        id=20,
        extracted_text=None,
        review_pages=[],
        ocr_revision=3,
        review_status=ReviewStatus.IN_PROGRESS.value,
        reviewed_by=None,
        reviewed_at=None,
    )


def test_update_ocr_element_checks_version_after_loading_locked_rows():
    document = editable_document()
    element = SimpleNamespace(id=30, text="before", version=2, is_in_content=True)
    service, db, repository = build_service(document=document, element=element)

    updated = service.update_ocr_element(10, 20, 30, "after", 2, 7)

    repository.get_by_id_for_update_with_review.assert_called_once_with(10, 20)
    repository.get_ocr_element_for_update.assert_called_once_with(10, 20, 30)
    assert updated is element
    assert element.text == "after"
    assert element.version == 3
    assert document.ocr_revision == 4
    db.commit.assert_called_once()


def test_update_ocr_element_rolls_back_stale_version_without_mutation():
    document = editable_document()
    element = SimpleNamespace(id=30, text="current", version=4, is_in_content=True)
    service, db, _ = build_service(document=document, element=element)

    with pytest.raises(BusinessError) as error:
        service.update_ocr_element(10, 20, 30, "stale edit", 3, 7)

    assert error.value.error_code is ErrorCode.OCR_EDIT_CONFLICT
    assert element.text == "current"
    assert element.version == 4
    assert document.ocr_revision == 3
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_exclusion_uses_same_locked_version_check():
    document = editable_document()
    element = SimpleNamespace(id=30, is_excluded=False, version=2, is_in_content=True)
    service, db, repository = build_service(document=document, element=element)

    updated = service.set_ocr_element_exclusion(10, 20, 30, True, 2)

    repository.get_by_id_for_update.assert_called_once_with(10, 20)
    repository.get_ocr_element_for_update.assert_called_once_with(10, 20, 30)
    assert updated.is_excluded is True
    assert updated.version == 3
    assert document.ocr_revision == 4
    db.commit.assert_called_once()


def test_complete_review_locks_document_before_updating_completion_state():
    document = editable_document()
    document.review_pages = []
    service, db, repository = build_service(document=document)

    completed = service.complete_ocr_review(10, 20, 7)

    repository.get_by_id_for_update_with_review.assert_called_once_with(10, 20)
    assert completed.review_status == ReviewStatus.COMPLETED.value
    assert completed.reviewed_by == 7
    assert completed.reviewed_at is not None
    db.commit.assert_called_once()


def test_update_uses_element_range_instead_of_first_matching_text():
    document = editable_document()
    document.extracted_text = SimpleNamespace(content="same\nnative same\nsame", char_count=21, ocr_char_count=8, text_version=1)
    first = SimpleNamespace(id=30, text="same", version=1, is_in_content=True, is_deleted=False, content_start=0, content_end=4)
    selected = SimpleNamespace(id=31, text="same", version=1, is_in_content=True, is_deleted=False, content_start=17, content_end=21)
    document.review_pages = [SimpleNamespace(elements=[first, selected])]
    service, _, repository = build_service(document=document, element=selected)

    service.update_ocr_element(10, 20, 31, "changed", 1, 7)

    assert document.extracted_text.content == "same\nnative same\nchanged"
    assert first.content_start == 0
    assert selected.content_end == 24
    repository.get_ocr_element_for_update.assert_called_once_with(10, 20, 31)


def test_complete_review_restores_previously_excluded_element_at_saved_range():
    document = editable_document()
    document.extracted_text = SimpleNamespace(content="first\n\nlast", char_count=11, ocr_char_count=9, text_version=2, is_confirmed=False, confirmed_by=None, confirmed_at=None)
    first = SimpleNamespace(id=30, text="first", is_excluded=False, is_in_content=True, is_deleted=False, content_start=0, content_end=5)
    restored = SimpleNamespace(id=31, text="middle", is_excluded=False, is_in_content=False, is_deleted=False, content_start=6, content_end=6)
    last = SimpleNamespace(id=32, text="last", is_excluded=False, is_in_content=True, is_deleted=False, content_start=7, content_end=11)
    document.review_pages = [SimpleNamespace(elements=[first, restored, last])]
    service, _, _ = build_service(document=document)

    service.complete_ocr_review(10, 20, 7)

    assert document.extracted_text.content == "first\nmiddle\nlast"
    assert restored.is_in_content is True
    assert restored.content_end == 12
    assert last.content_start == 13


def batch_element(element_id, text, start, end, *, version=1, element_type="TEXT_LINE"):
    return SimpleNamespace(
        id=element_id,
        text=text,
        version=version,
        is_in_content=True,
        is_deleted=False,
        is_excluded=False,
        is_paragraph_start=False,
        element_type=element_type,
        element_type_source="AUTO",
        x=0.1,
        y=0.1,
        width=0.4,
        height=0.05,
        content_start=start,
        content_end=end,
    )


def test_batch_update_rebuilds_content_and_increments_document_versions_once():
    document = editable_document()
    document.review_status = ReviewStatus.COMPLETED.value
    document.extracted_text = SimpleNamespace(
        content="first\nsecond\nthird",
        char_count=18,
        ocr_char_count=16,
        text_version=4,
        is_confirmed=True,
        confirmed_by=7,
        confirmed_at=object(),
    )
    first = batch_element(30, "first", 0, 5)
    second = batch_element(31, "second", 6, 12)
    third = batch_element(32, "third", 13, 18)
    document.review_pages = [SimpleNamespace(elements=[first, second, third])]
    service, db, repository = build_service(document=document)
    repository.get_ocr_elements_for_update.return_value = [first, second]

    updated_document, updated = service.update_ocr_elements_batch(
        10,
        20,
        [
            OcrElementBatchChange(id=30, version=1, text="FIRST"),
            OcrElementBatchChange(id=31, version=1, text="second expanded"),
        ],
        7,
    )

    repository.get_by_id_for_update_with_review.assert_called_once_with(10, 20)
    repository.get_by_id_for_update.assert_not_called()
    assert updated == [first, second]
    assert updated_document.extracted_text.content == "FIRST\nsecond expanded\nthird"
    assert (first.content_start, first.content_end) == (0, 5)
    assert (second.content_start, second.content_end) == (6, 21)
    assert (third.content_start, third.content_end) == (22, 27)
    assert first.version == 2
    assert second.version == 2
    assert document.ocr_revision == 4
    assert document.extracted_text.text_version == 5
    assert document.review_status == ReviewStatus.IN_PROGRESS.value
    assert document.extracted_text.is_confirmed is False
    assert db.add.call_count == 2
    db.commit.assert_called_once()


def test_batch_update_rolls_back_all_items_on_stale_version():
    document = editable_document()
    first = batch_element(30, "first", 0, 5, version=2)
    second = batch_element(31, "second", 6, 12, version=3)
    document.review_pages = [SimpleNamespace(elements=[first, second])]
    service, db, repository = build_service(document=document)
    repository.get_ocr_elements_for_update.return_value = [first, second]

    with pytest.raises(BusinessError) as error:
        service.update_ocr_elements_batch(
            10,
            20,
            [
                OcrElementBatchChange(id=30, version=2, text="changed"),
                OcrElementBatchChange(id=31, version=2, is_excluded=True),
            ],
            7,
        )

    assert error.value.error_code is ErrorCode.OCR_EDIT_CONFLICT
    assert first.text == "first"
    assert second.is_excluded is False
    assert document.ocr_revision == 3
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_batch_paragraph_change_marks_chunks_stale_once():
    document = editable_document()
    document.extracted_text = SimpleNamespace(
        content="heading\nbody",
        char_count=12,
        ocr_char_count=11,
        text_version=2,
        is_confirmed=False,
        confirmed_by=None,
        confirmed_at=None,
    )
    heading = batch_element(30, "heading", 0, 7)
    body = batch_element(31, "body", 8, 12)
    document.review_pages = [SimpleNamespace(elements=[heading, body])]
    service, _, repository = build_service(document=document)
    repository.get_ocr_elements_for_update.return_value = [heading, body]

    service.update_ocr_elements_batch(
        10,
        20,
        [
            OcrElementBatchChange(id=30, version=1, element_type="HEADING"),
            OcrElementBatchChange(id=31, version=1, is_paragraph_start=True),
        ],
        7,
    )

    assert heading.element_type == "HEADING"
    assert heading.element_type_source == "USER_CORRECTED"
    assert heading.is_paragraph_start is True
    assert body.is_paragraph_start is True
    assert document.ocr_revision == 4
    assert document.extracted_text.text_version == 3


def test_batch_geometry_change_updates_box_without_changing_text_version():
    document = editable_document()
    element = batch_element(30, "box", 0, 3)
    document.review_pages = [SimpleNamespace(elements=[element])]
    service, _, repository = build_service(document=document)
    repository.get_ocr_elements_for_update.return_value = [element]

    service.update_ocr_elements_batch(
        10,
        20,
        [OcrElementBatchChange(id=30, version=1, x=0.2, y=0.3, width=0.5, height=0.1)],
        7,
    )

    assert (element.x, element.y, element.width, element.height) == (0.2, 0.3, 0.5, 0.1)
    assert element.version == 2
    assert document.ocr_revision == 4
    assert document.extracted_text.text_version == 2

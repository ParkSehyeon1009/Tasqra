from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.extractors.protocol import ExtractResult
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.models.enums import DocumentStatus
from app.services.extraction_service import ExtractionService


def test_upload_creates_pending_document_without_running_extractor(monkeypatch):
    db = MagicMock()
    documents = MagicMock()
    documents.get_by_content_hash.return_value = None
    documents.create.side_effect = lambda document: document
    extractors = MagicMock()
    service = ExtractionService(db, documents, extractors)
    monkeypatch.setattr(service, "_save_file", lambda _extension, _content: "uploads/document.pdf")

    document = service.create_pending_upload(10, 20, "document.pdf", b"content")

    assert document.status == DocumentStatus.PENDING.value
    assert document.extracted_text is None
    extractors.get.assert_not_called()
    db.commit.assert_called_once()


def test_worker_moves_document_to_extracted():
    db = MagicMock()
    document = SimpleNamespace(
        id=30,
        file_type="pdf",
        storage_path="uploads/document.pdf",
        extraction_strategy="AUTO",
        status=DocumentStatus.PENDING.value,
        processing_error=None,
        extracted_text=None,
        review_pages=[],
        processing_mode="NORMAL",
        review_status="NOT_REQUIRED",
    )
    documents = MagicMock()
    documents.get_by_id.return_value = document
    extractor = MagicMock()
    extractor.extract.return_value = ExtractResult("text", 1, 4, 4, 0, "TEXT_LAYER")
    extractors = MagicMock()
    extractors.get.return_value = extractor

    processed = ExtractionService(db, documents, extractors).process_document(10, 30)

    assert processed.status == DocumentStatus.EXTRACTED.value
    assert processed.extracted_text.content == "text"
    assert processed.processing_error is None
    assert db.commit.call_count == 2


def test_worker_records_failure_reason():
    db = MagicMock()
    document = SimpleNamespace(
        id=30,
        file_type="pdf",
        storage_path="uploads/document.pdf",
        extraction_strategy="AUTO",
        status=DocumentStatus.PENDING.value,
        processing_error=None,
    )
    documents = MagicMock()
    documents.get_by_id.return_value = document
    extractor = MagicMock()
    extractor.extract.side_effect = RuntimeError("secret internal detail")
    extractors = MagicMock()
    extractors.get.return_value = extractor

    with pytest.raises(Exception):
        ExtractionService(db, documents, extractors).process_document(10, 30)

    assert document.status == DocumentStatus.FAILED.value
    assert document.processing_error == "문서에서 텍스트를 추출할 수 없습니다."


def test_failed_document_can_be_prepared_for_retry():
    db = MagicMock()
    document = SimpleNamespace(status=DocumentStatus.FAILED.value, processing_error="failed")
    documents = MagicMock()
    documents.get_by_id_for_update.return_value = document

    retried = ExtractionService(db, documents, MagicMock()).prepare_retry(10, 30)

    assert retried.status == DocumentStatus.PENDING.value
    assert retried.processing_error is None
    db.commit.assert_called_once()


def test_processing_document_cannot_be_queued_twice():
    document = SimpleNamespace(status=DocumentStatus.EXTRACTING.value, processing_error=None)
    documents = MagicMock()
    documents.get_by_id_for_update.return_value = document

    with pytest.raises(BusinessError) as caught:
        ExtractionService(MagicMock(), documents, MagicMock()).prepare_retry(10, 30)

    assert caught.value.error_code is ErrorCode.DOCUMENT_RETRY_NOT_ALLOWED

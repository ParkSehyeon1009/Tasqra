from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.services.extraction_service import ExtractionService


def build_service():
    db = MagicMock()
    documents = MagicMock()
    extractors = MagicMock()
    return ExtractionService(db, documents, extractors), documents, extractors


def test_duplicate_file_is_rejected_before_storage_or_extraction(monkeypatch):
    service, documents, extractors = build_service()
    documents.get_by_content_hash.return_value = SimpleNamespace(filename="기존.pdf")
    save_file = MagicMock()
    monkeypatch.setattr(service, "_save_file", save_file)

    with pytest.raises(BusinessError) as caught:
        service.upload_and_extract(10, 20, "새이름.pdf", b"same-content")

    assert caught.value.error_code is ErrorCode.DUPLICATE_DOCUMENT
    assert "기존.pdf" in caught.value.detail
    save_file.assert_not_called()
    extractors.get.assert_not_called()


def test_duplicate_check_is_scoped_to_requested_project(monkeypatch):
    service, documents, _ = build_service()
    documents.get_by_content_hash.return_value = SimpleNamespace(filename="기존.pdf")
    monkeypatch.setattr(service, "_save_file", MagicMock())

    with pytest.raises(BusinessError):
        service.upload_and_extract(77, 20, "문서.pdf", b"content")

    project_id, content_hash = documents.get_by_content_hash.call_args.args
    assert project_id == 77
    assert len(content_hash) == 64

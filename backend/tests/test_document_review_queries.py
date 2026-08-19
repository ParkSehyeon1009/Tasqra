from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.services.document_service import DocumentService


def build_service():
    db = MagicMock()
    documents = MagicMock()
    analyses = MagicMock()
    return DocumentService(db, documents, analyses), documents


def test_review_document_uses_review_eager_loading_query():
    service, documents = build_service()
    expected = SimpleNamespace(id=20)
    documents.get_by_id_with_review.return_value = expected

    result = service.get_document_for_review(10, 20)

    assert result is expected
    documents.get_by_id_with_review.assert_called_once_with(10, 20)
    documents.get_by_id.assert_not_called()


def test_review_document_raises_not_found():
    service, documents = build_service()
    documents.get_by_id_with_review.return_value = None

    with pytest.raises(BusinessError) as error:
        service.get_document_for_review(10, 20)

    assert error.value.error_code is ErrorCode.DOCUMENT_NOT_FOUND

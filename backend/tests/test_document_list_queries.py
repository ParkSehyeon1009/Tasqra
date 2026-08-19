from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.enums import AnalyzerType
from app.services.document_service import DocumentService


def test_document_list_loads_latest_analyses_in_one_batch():
    db = MagicMock()
    documents = MagicMock()
    analyses = MagicMock()
    service = DocumentService(db, documents, analyses)

    first = SimpleNamespace(id=1)
    second = SimpleNamespace(id=2)
    documents.search.return_value = ([first, second], 2)
    analyses.get_latest_by_types.return_value = {
        (1, AnalyzerType.CATEGORY.value): SimpleNamespace(
            result_json={"category": "계약서"}
        ),
        (1, AnalyzerType.SUMMARY.value): SimpleNamespace(
            result_json={"summary": "첫 번째 문서 요약"}
        ),
        (2, AnalyzerType.SUMMARY.value): SimpleNamespace(
            result_json={"summary": "두 번째 문서 요약"}
        ),
    }

    rows, total, total_pages = service.search_documents(
        project_id=10,
        q=None,
        document_type=None,
        category=None,
        page=1,
        size=20,
    )

    analyses.get_latest_by_types.assert_called_once_with(
        [1, 2],
        [AnalyzerType.CATEGORY.value, AnalyzerType.SUMMARY.value],
    )
    analyses.get_latest_by_type.assert_not_called()
    assert total == 2
    assert total_pages == 1
    assert rows[0].category == "계약서"
    assert rows[0].summary_preview == "첫 번째 문서 요약"
    assert rows[1].category is None
    assert rows[1].summary_preview == "두 번째 문서 요약"

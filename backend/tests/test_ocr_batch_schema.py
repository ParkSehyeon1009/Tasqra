import pytest
from pydantic import ValidationError

from app.schemas.document import OcrElementBatchUpdateRequest


def test_batch_request_accepts_partial_updates():
    request = OcrElementBatchUpdateRequest.model_validate({
        "items": [
            {"id": 12, "version": 3, "text": "수정된 텍스트"},
            {"id": 15, "version": 1, "is_excluded": True},
            {"id": 18, "version": 2, "is_paragraph_start": True},
        ]
    })

    assert len(request.items) == 3


@pytest.mark.parametrize(
    "items",
    [
        [{"id": 12, "version": 1}],
        [
            {"id": 12, "version": 1, "text": "첫 번째"},
            {"id": 12, "version": 1, "text": "중복"},
        ],
    ],
)
def test_batch_request_rejects_empty_changes_and_duplicate_ids(items):
    with pytest.raises(ValidationError):
        OcrElementBatchUpdateRequest.model_validate({"items": items})

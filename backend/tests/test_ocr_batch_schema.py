import pytest
from pydantic import ValidationError

from app.schemas.document import OcrElementBatchUpdateRequest


def test_batch_request_accepts_partial_updates():
    request = OcrElementBatchUpdateRequest.model_validate({
        "items": [
            {"id": 12, "version": 3, "text": "수정된 텍스트"},
            {"id": 15, "version": 1, "is_excluded": True},
            {"id": 18, "version": 2, "is_paragraph_start": True},
            {"id": 19, "version": 1, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
            {"id": 20, "version": 1, "is_reviewed": True},
            {"id": 21, "version": 1, "is_deleted": True},
        ]
    })

    assert len(request.items) == 6


@pytest.mark.parametrize(
    "item",
    [
        {"id": 1, "version": 1, "x": -0.1},
        {"id": 1, "version": 1, "width": 0},
        {"id": 1, "version": 1, "x": 0.8, "width": 0.3},
        {"id": 1, "version": 1, "y": 0.9, "height": 0.2},
    ],
)
def test_batch_request_rejects_invalid_geometry(item):
    with pytest.raises(ValidationError):
        OcrElementBatchUpdateRequest.model_validate({"items": [item]})


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

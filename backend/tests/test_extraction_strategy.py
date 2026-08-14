import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.extractors.pdf_extractor import PdfExtractor
from app.models.enums import DocumentType, ExtractionStrategy
from app.services.extraction_service import ExtractionService


class EmptyPdfPage:
    def get_text(self, format_name):
        assert format_name == "dict"
        return {"blocks": []}


def test_pdf_text_only_does_not_fallback_to_ocr(monkeypatch):
    extractor = PdfExtractor(ocr=None)

    def fail_if_called(_page):
        raise AssertionError("TEXT_ONLY must not run full-page OCR")

    monkeypatch.setattr(extractor, "_extract_full_page_with_ocr", fail_if_called)

    elements, has_text, has_ocr = extractor._extract_page(
        EmptyPdfPage(),
        include_image_ocr=False,
    )

    assert elements == []
    assert has_text is False
    assert has_ocr is False


@pytest.mark.parametrize("file_type", ["pdf", "docx", "hwpx"])
@pytest.mark.parametrize("value", ["AUTO", "TEXT_ONLY", "TEXT_WITH_IMAGE_OCR"])
def test_document_files_accept_all_extraction_strategies(file_type, value):
    assert ExtractionService._validate_extraction_strategy(file_type, value) is ExtractionStrategy(value)


def test_image_files_only_accept_auto_strategy():
    with pytest.raises(BusinessError) as caught:
        ExtractionService._validate_extraction_strategy("png", "TEXT_ONLY")

    assert caught.value.error_code is ErrorCode.INVALID_EXTRACTION_STRATEGY


def test_document_type_is_normalized_and_validated():
    assert ExtractionService._validate_document_type(" report ") is DocumentType.REPORT
    assert ExtractionService._validate_document_type("") is None

    with pytest.raises(BusinessError) as caught:
        ExtractionService._validate_document_type("UNKNOWN")

    assert caught.value.error_code is ErrorCode.INVALID_DOCUMENT_TYPE

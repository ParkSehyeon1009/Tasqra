import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.extractors.layout import LayoutElement
from app.extractors.pdf_extractor import PdfExtractor
from app.models.enums import DocumentType, ExtractionStrategy
from app.services.extraction_service import ExtractionService


class EmptyPdfPage:
    def get_text(self, format_name):
        assert format_name == "dict"
        return {"blocks": []}


class PdfPage:
    def __init__(self, blocks):
        self._blocks = blocks
        self.rect = type("Rect", (), {"width": 600, "height": 800})()

    def get_text(self, format_name):
        assert format_name == "dict"
        return {"blocks": self._blocks}


def text_block(text, bbox):
    return {
        "type": 0,
        "bbox": bbox,
        "lines": [{"bbox": bbox, "spans": [{"text": text}]}],
    }


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


def test_large_scanned_page_with_sparse_text_layer_runs_full_page_ocr(monkeypatch):
    page = PdfPage([
        text_block("1", (280, 760, 290, 775)),
        text_block("워터마크", (250, 380, 350, 400)),
        {"type": 1, "bbox": (0, 0, 600, 800), "image": b"scan"},
    ])
    extractor = PdfExtractor(ocr=None)
    full_page = [
        LayoutElement(
            x=250,
            y=380,
            x2=350,
            y2=400,
            content="스캔 본문",
            source="ocr",
        )
    ]
    monkeypatch.setattr(
        extractor,
        "_extract_full_page_with_ocr",
        lambda _page: full_page,
    )

    elements, has_text, has_ocr = extractor._extract_page(page)

    assert has_ocr is True
    assert [element.content for element in elements if element.source == "ocr"] == [
        "스캔 본문"
    ]
    assert "워터마크" not in [element.content for element in elements]
    assert has_text is True  # OCR과 겹치지 않은 페이지 번호는 보존한다.


def test_sparse_born_digital_page_without_large_image_does_not_run_ocr(monkeypatch):
    page = PdfPage([text_block("짧은 안내", (50, 50, 180, 75))])
    extractor = PdfExtractor(ocr=None)

    def fail_if_called(_page):
        raise AssertionError("sparse text-only pages must not run OCR")

    monkeypatch.setattr(extractor, "_extract_full_page_with_ocr", fail_if_called)

    elements, has_text, has_ocr = extractor._extract_page(page)

    assert [element.content for element in elements] == ["짧은 안내"]
    assert has_text is True
    assert has_ocr is False


def test_large_image_with_sufficient_text_layer_does_not_run_full_page_ocr(monkeypatch):
    page = PdfPage([
        text_block("충분한 텍스트 레이어가 이미 존재하는 첫 번째 본문입니다.", (40, 80, 560, 110)),
        text_block("충분한 텍스트 레이어가 이미 존재하는 두 번째 본문입니다.", (40, 120, 560, 150)),
        {"type": 1, "bbox": (0, 0, 600, 800), "image": b"background"},
    ])
    extractor = PdfExtractor(ocr=None)

    def fail_if_called(_page):
        raise AssertionError("sufficient text layers must not run full-page OCR")

    monkeypatch.setattr(extractor, "_extract_full_page_with_ocr", fail_if_called)

    _, has_text, has_ocr = extractor._extract_page(page)

    assert has_text is True
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

import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from docx import Document

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.extractors.docx_extractor import DocxExtractor
from app.extractors.hwpx_extractor import HwpxExtractor
from app.extractors.protocol import ExtractResult
from app.services.extraction_service import ExtractionService


def test_docx_rejects_native_text_before_image_ocr(tmp_path):
    path = tmp_path / "oversized.docx"
    document = Document()
    document.add_paragraph("본문 여섯글자")
    document.save(path)
    ocr = MagicMock()

    with pytest.raises(BusinessError) as caught:
        DocxExtractor(ocr).extract(str(path), max_text_chars=5)

    assert caught.value.error_code is ErrorCode.CONTENT_TOO_LARGE
    ocr.extract.assert_not_called()


def test_hwpx_rejects_native_text_before_image_ocr(tmp_path):
    path = tmp_path / "oversized.hwpx"
    section = """<?xml version="1.0" encoding="UTF-8"?>
    <hs:sec xmlns:hs="urn:hancom:section" xmlns:hp="urn:hancom:paragraph">
      <hp:p><hp:run><hp:t>본문 여섯글자</hp:t></hp:run></hp:p>
    </hs:sec>
    """
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", section)
    ocr = MagicMock()

    with pytest.raises(BusinessError) as caught:
        HwpxExtractor(ocr).extract(str(path), max_text_chars=5)

    assert caught.value.error_code is ErrorCode.CONTENT_TOO_LARGE
    ocr.extract.assert_not_called()


def test_embedded_image_ocr_text_does_not_count_toward_document_limit(monkeypatch):
    monkeypatch.setattr(settings, "MAX_EXTRACTED_CHARS", 2)
    result = ExtractResult(
        content="본문\n" + "이미지" * 100,
        page_count=1,
        char_count=303,
        text_char_count=2,
        ocr_char_count=300,
        extract_method="DOCX",
    )

    ExtractionService._validate_result("docx", result)


def test_service_passes_native_text_limit_to_document_extractor(monkeypatch):
    extractor = MagicMock()
    extractor.extract.return_value = ExtractResult(
        content="본문",
        page_count=1,
        char_count=2,
        text_char_count=2,
        ocr_char_count=0,
        extract_method="DOCX",
    )
    registry = MagicMock()
    registry.get.return_value = extractor
    service = ExtractionService(MagicMock(), MagicMock(), registry)
    document = SimpleNamespace(
        id=1,
        file_type="docx",
        storage_path="document.docx",
        extraction_strategy="AUTO",
        filename="document.docx",
    )

    service._extract(document)

    extractor.extract.assert_called_once()
    assert extractor.extract.call_args.kwargs == {
        "include_image_ocr": True,
        "max_text_chars": settings.MAX_EXTRACTED_CHARS,
    }

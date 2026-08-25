import zipfile
from io import BytesIO
from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

from PIL import Image

from app.extractors.docx_extractor import DocxExtractor
from app.extractors.hwpx_extractor import HwpxExtractor
from app.extractors.image_extractor import ImageExtractor
from app.extractors.layout import LayoutElement


def _rotated_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (40, 20), "white")
    exif = Image.Exif()
    exif[274] = 6
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def _ocr_element() -> LayoutElement:
    return LayoutElement(
        x=1,
        y=2,
        x2=11,
        y2=12,
        content="본문",
        source="ocr",
        confidence=0.9,
    )


def test_image_extractor_uses_exif_normalized_image_for_ocr_and_review(tmp_path):
    path = tmp_path / "rotated.jpg"
    path.write_bytes(_rotated_jpeg_bytes())
    ocr = MagicMock()
    ocr.extract.return_value = [_ocr_element()]

    result = ImageExtractor(ocr).extract(str(path))

    ocr_image = ocr.extract.call_args.args[0]
    assert ocr_image.size == (20, 40)
    assert ocr.extract.call_args.kwargs == {"normalize_orientation": False}
    assert (result.review_pages[0].width, result.review_pages[0].height) == (20, 40)


def test_docx_embedded_image_review_uses_same_exif_orientation_as_ocr():
    ocr = MagicMock()
    ocr.extract.return_value = [_ocr_element()]

    _, page, _ = DocxExtractor(ocr)._ocr_image(_rotated_jpeg_bytes(), 1)

    ocr_image = ocr.extract.call_args.args[0]
    assert ocr_image.size == (20, 40)
    assert ocr.extract.call_args.kwargs == {"normalize_orientation": False}
    assert (page.width, page.height) == (20, 40)


def test_hwpx_embedded_image_review_uses_same_exif_orientation_as_ocr():
    ocr = MagicMock()
    ocr.extract.return_value = [_ocr_element()]
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("BinData/image.jpg", _rotated_jpeg_bytes())
    archive_buffer.seek(0)

    review_pages = []
    counts = {"text": 0, "ocr": 0}
    picture = ET.fromstring('<pic><img binaryItemIDRef="image1" /></pic>')
    with zipfile.ZipFile(archive_buffer) as archive:
        text = HwpxExtractor(ocr)._extract_picture(
            picture,
            archive,
            {"image1": "BinData/image.jpg"},
            review_pages,
            counts,
        )

    ocr_image = ocr.extract.call_args.args[0]
    assert text
    assert ocr_image.size == (20, 40)
    assert ocr.extract.call_args.kwargs == {"normalize_orientation": False}
    assert (review_pages[0].width, review_pages[0].height) == (20, 40)


def test_transparent_image_has_white_background_in_ocr_and_review(tmp_path):
    path = tmp_path / "transparent.png"
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(path)
    ocr = MagicMock()
    ocr.extract.return_value = []

    result = ImageExtractor(ocr).extract(str(path))

    ocr_image = ocr.extract.call_args.args[0]
    assert ocr_image.getpixel((0, 0)) == (255, 255, 255)
    with Image.open(BytesIO(result.review_pages[0].image_bytes)) as review_image:
        assert review_image.getpixel((0, 0)) == (255, 255, 255)

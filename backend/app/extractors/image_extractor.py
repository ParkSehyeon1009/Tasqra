from PIL import Image

from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.protocol import ExtractResult, TextExtractor
from app.models.enums import ExtractMethod


class ImageExtractor(TextExtractor):
    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(self, file_path: str) -> ExtractResult:
        with Image.open(file_path) as source_image:
            image = source_image.copy()
            elements = self._ocr.extract(image)

        content = "\n".join(
            element.content
            for element in elements
        )

        return ExtractResult(
            content=content,
            page_count=1,
            char_count=len(content),
            extract_method=ExtractMethod.OCR.value,
        )

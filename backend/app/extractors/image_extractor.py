from io import BytesIO
from PIL import Image

from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.protocol import ExtractedElement, ExtractedPage, ExtractResult, TextExtractor
from app.models.enums import ExtractMethod


class ImageExtractor(TextExtractor):
    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(self, file_path: str) -> ExtractResult:
        with Image.open(file_path) as source_image:
            image = source_image.copy()
            elements = self._ocr.extract(image)

        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        width, height = image.size
        review_elements = tuple(
            ExtractedElement(
                x=max(0.0, min(1.0, element.x / width)),
                y=max(0.0, min(1.0, element.y / height)),
                width=max(0.0, min(1.0, ((element.x2 if element.x2 is not None else element.x) - element.x) / width)),
                height=max(0.0, min(1.0, ((element.y2 if element.y2 is not None else element.y) - element.y) / height)),
                text=element.content,
                confidence=element.confidence,
            ) for element in elements if element.content.strip()
        )

        content = "\n".join(
            element.content
            for element in elements
        )

        return ExtractResult(
            content=content,
            page_count=1,
            char_count=len(content),
            text_char_count=0,
            ocr_char_count=sum(len(element.text) for element in review_elements),
            extract_method=ExtractMethod.OCR.value,
            review_pages=(ExtractedPage(1, width, height, buffer.getvalue(), review_elements),),
        )

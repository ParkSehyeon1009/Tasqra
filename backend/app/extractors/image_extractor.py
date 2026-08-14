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
        review_elements = []
        content_parts = []
        content_cursor = 0
        for element in elements:
            content_parts.append(element.content)
            if element.content.strip():
                review_elements.append(ExtractedElement(
                    x=max(0.0, min(1.0, element.x / width)),
                    y=max(0.0, min(1.0, element.y / height)),
                    width=max(0.0, min(1.0, ((element.x2 if element.x2 is not None else element.x) - element.x) / width)),
                    height=max(0.0, min(1.0, ((element.y2 if element.y2 is not None else element.y) - element.y) / height)),
                    text=element.content,
                    confidence=element.confidence,
                    content_start=content_cursor,
                    content_end=content_cursor + len(element.content),
                    element_type=element.element_type,
                    element_type_source=element.element_type_source,
                    is_paragraph_start=element.is_paragraph_start,
                    table_id=element.table_id,
                    table_row=element.table_row,
                ))
            content_cursor += len(element.content) + 1

        content = "\n".join(content_parts)

        return ExtractResult(
            content=content,
            page_count=1,
            char_count=len(content),
            text_char_count=0,
            ocr_char_count=sum(len(element.text) for element in review_elements),
            extract_method=ExtractMethod.OCR.value,
            review_pages=(ExtractedPage(1, width, height, buffer.getvalue(), tuple(review_elements)),),
        )

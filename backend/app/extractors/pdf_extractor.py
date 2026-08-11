from io import BytesIO
from typing import Any

import fitz
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.extractors.layout import LayoutElement
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.protocol import ExtractedElement, ExtractedPage, ExtractResult, TextExtractor
from app.extractors.reading_order import build_reading_groups
from app.models.enums import ExtractMethod


class PdfExtractor(TextExtractor):
    _LINE_OVERLAP_RATIO = 0.45

    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(self, file_path: str) -> ExtractResult:
        page_contents: list[str] = []
        review_pages: list[ExtractedPage] = []

        has_text = False
        has_ocr = False

        with fitz.open(file_path) as document:
            page_count = len(document)

            if page_count > settings.MAX_PAGES:
                raise BusinessError(
                    ErrorCode.TOO_MANY_PAGES,
                    detail=f"PDF는 최대 {settings.MAX_PAGES}페이지까지 업로드할 수 있습니다.",
                )

            for page in document:
                elements, page_has_text, page_has_ocr = self._extract_page(page)

                has_text = has_text or page_has_text
                has_ocr = has_ocr or page_has_ocr

                if page_has_text and not page_has_ocr:
                    elements = self._order_text_layer_elements(
                        elements,
                        page_width=float(page.rect.width),
                        page_left=float(page.rect.x0),
                    )
                elif page_has_text:
                    elements = self._order_hybrid_elements(
                        elements,
                        page_width=float(page.rect.width),
                        page_left=float(page.rect.x0),
                    )

                if page_has_ocr:
                    review_pages.append(self._build_review_page(page, elements, len(page_contents) + 1))

                page_content = "\n".join(
                    element.content
                    for element in elements
                    if element.content.strip()
                )

                page_contents.append(page_content)

        content = "\n\n".join(page_contents)

        if has_text and has_ocr:
            extract_method = ExtractMethod.HYBRID.value
        elif has_ocr:
            extract_method = ExtractMethod.OCR.value
        else:
            extract_method = ExtractMethod.TEXT_LAYER.value

        return ExtractResult(
            content=content,
            page_count=page_count,
            char_count=len(content),
            extract_method=extract_method,
            review_pages=tuple(review_pages),
        )

    @staticmethod
    def _build_review_page(page: fitz.Page, elements: list[LayoutElement], page_number: int) -> ExtractedPage:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        page_width = max(float(page.rect.width), 1.0)
        page_height = max(float(page.rect.height), 1.0)
        review_elements = []
        for element in elements:
            if element.source != "ocr" or not element.content.strip():
                continue
            x2 = element.x2 if element.x2 is not None else element.x
            y2 = element.y2 if element.y2 is not None else element.y
            review_elements.append(ExtractedElement(
                x=max(0.0, min(1.0, element.x / page_width)),
                y=max(0.0, min(1.0, element.y / page_height)),
                width=max(0.0, min(1.0, (x2 - element.x) / page_width)),
                height=max(0.0, min(1.0, (y2 - element.y) / page_height)),
                text=element.content, confidence=element.confidence,
            ))
        return ExtractedPage(page_number, pixmap.width, pixmap.height, pixmap.tobytes("png"), tuple(review_elements))

    def _extract_page(
        self,
        page: fitz.Page,
    ) -> tuple[list[LayoutElement], bool, bool]:
        page_dict: dict[str, Any] = page.get_text("dict")

        elements: list[LayoutElement] = []
        has_text = False
        has_ocr = False

        blocks = page_dict.get("blocks", [])

        for block in blocks:
            block_type = block.get("type")

            if block_type == 0:
                text_elements = self._extract_text_block(block)

                if text_elements:
                    elements.extend(text_elements)
                    has_text = True

        for block in blocks:
            if block.get("type") == 1:
                if self._image_contains_text_layer(block, elements):
                    continue
                image_elements = self._extract_image_block(block)

                if image_elements:
                    elements.extend(image_elements)
                    has_ocr = True

        # 텍스트와 이미지 OCR 결과가 모두 없으면 페이지 전체를 OCR한다.
        if not elements:
            page_ocr_elements = self._extract_full_page_with_ocr(page)

            if page_ocr_elements:
                elements.extend(page_ocr_elements)
                has_ocr = True

        return elements, has_text, has_ocr

    @staticmethod
    def _image_contains_text_layer(
        block: dict[str, Any],
        text_elements: list[LayoutElement],
    ) -> bool:
        bbox = block.get("bbox", (0, 0, 0, 0))
        x0, y0, x1, y1 = (float(value) for value in bbox)
        contained_count = 0

        for element in text_elements:
            if element.source != "text":
                continue
            element_x2 = element.x2 if element.x2 is not None else element.x
            element_y2 = element.y2 if element.y2 is not None else element.y
            center_x = (element.x + element_x2) / 2
            center_y = (element.y + element_y2) / 2
            if x0 <= center_x <= x1 and y0 <= center_y <= y1:
                contained_count += 1
                if contained_count >= 2:
                    return True

        return False

    @staticmethod
    def _extract_text_block(
        block: dict[str, Any],
    ) -> list[LayoutElement]:
        elements: list[LayoutElement] = []

        for line in block.get("lines", []):
            spans: list[str] = []

            for span in line.get("spans", []):
                text = str(span.get("text", "")).strip()

                if text:
                    spans.append(text)

            line_text = " ".join(spans).strip()

            if line_text:
                bbox = line.get("bbox", block.get("bbox", (0, 0, 0, 0)))
                elements.append(
                    LayoutElement(
                        x=float(bbox[0]),
                        y=float(bbox[1]),
                        x2=float(bbox[2]),
                        y2=float(bbox[3]),
                        content=line_text,
                        source="text",
                    )
                )

        return elements

    @classmethod
    def _order_text_layer_elements(
        cls,
        elements: list[LayoutElement],
        *,
        page_width: float,
        page_left: float,
    ) -> list[LayoutElement]:
        groups = build_reading_groups(
            elements,
            [],
            page_width=page_width,
            page_left=page_left,
        )
        if groups is None:
            merged = cls._merge_text_layer_elements(elements)
            merged.sort(key=lambda element: (element.y, element.x))
            return merged

        ordered: list[LayoutElement] = []
        for group in groups:
            ordered.extend(cls._merge_text_layer_elements(group.elements))
        return ordered

    @classmethod
    def _order_hybrid_elements(
        cls,
        elements: list[LayoutElement],
        *,
        page_width: float,
        page_left: float,
    ) -> list[LayoutElement]:
        text_elements = [
            element for element in elements if element.source == "text"
        ]
        image_ocr_blocks = [
            element for element in elements if element.source == "ocr"
        ]
        groups = build_reading_groups(
            text_elements,
            image_ocr_blocks,
            page_width=page_width,
            page_left=page_left,
        )
        if groups is None:
            merged = cls._merge_text_layer_elements(text_elements)
            merged.extend(image_ocr_blocks)
            merged.sort(key=lambda element: (element.y, element.x))
            return merged

        ordered: list[LayoutElement] = []
        for group in groups:
            if group.atomic:
                ordered.extend(group.elements)
            else:
                ordered.extend(cls._merge_text_layer_elements(group.elements))
        return ordered

    @classmethod
    def _merge_text_layer_elements(
        cls,
        elements: list[LayoutElement],
    ) -> list[LayoutElement]:
        """같은 줄의 PDF 텍스트 블록만 병합하고 OCR 요소는 그대로 둔다."""
        text_elements = [element for element in elements if element.source == "text"]
        other_elements = [element for element in elements if element.source != "text"]

        if len(text_elements) < 2:
            return elements

        lines: list[list[LayoutElement]] = []
        for element in sorted(text_elements, key=cls._vertical_sort_key):
            matching_line = next(
                (line for line in lines if cls._belongs_to_line(element, line)),
                None,
            )

            if matching_line is None:
                lines.append([element])
            else:
                matching_line.append(element)

        merged_text = [cls._merge_text_line(line) for line in lines]
        return merged_text + other_elements

    @staticmethod
    def _vertical_sort_key(element: LayoutElement) -> tuple[float, float]:
        y2 = element.y2 if element.y2 is not None else element.y
        return ((element.y + y2) / 2, element.x)

    @classmethod
    def _belongs_to_line(
        cls,
        element: LayoutElement,
        line: list[LayoutElement],
    ) -> bool:
        element_y2 = element.y2 if element.y2 is not None else element.y
        line_y1 = min(item.y for item in line)
        line_y2 = max(item.y2 if item.y2 is not None else item.y for item in line)

        element_height = max(element_y2 - element.y, 1.0)
        line_height = max(line_y2 - line_y1, 1.0)
        overlap = max(0.0, min(element_y2, line_y2) - max(element.y, line_y1))
        overlap_ratio = overlap / min(element_height, line_height)

        return overlap_ratio >= cls._LINE_OVERLAP_RATIO

    @staticmethod
    def _merge_text_line(line: list[LayoutElement]) -> LayoutElement:
        ordered = sorted(line, key=lambda element: element.x)

        return LayoutElement(
            x=min(element.x for element in ordered),
            y=min(element.y for element in ordered),
            x2=max(
                element.x2 if element.x2 is not None else element.x
                for element in ordered
            ),
            y2=max(
                element.y2 if element.y2 is not None else element.y
                for element in ordered
            ),
            content=" ".join(element.content for element in ordered),
            source="text",
        )

    def _extract_image_block(
        self,
        block: dict[str, Any],
    ) -> list[LayoutElement]:
        image_bytes = block.get("image")
        bbox = block.get("bbox", (0, 0, 0, 0))

        if not image_bytes:
            return []

        try:
            with Image.open(BytesIO(image_bytes)) as source_image:
                image = source_image.copy()

                image_width = image.width
                image_height = image.height

                if image_width <= 0 or image_height <= 0:
                    return []

                ocr_elements = self._ocr.extract(
                    image,
                    normalize_orientation=False,
                )

        except (UnidentifiedImageError, OSError, ValueError):
            return []

        if not ocr_elements:
            return []

        x0 = float(bbox[0])
        y0 = float(bbox[1])
        x1 = float(bbox[2])
        y1 = float(bbox[3])

        content = "\n".join(
            element.content
            for element in ocr_elements
            if element.content.strip()
        )
        recognized_char_count = sum(character.isalnum() for character in content)
        if not content or recognized_char_count < 2:
            return []

        confidences = [
            element.confidence
            for element in ocr_elements
            if element.confidence is not None
        ]
        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else None
        )

        return [
            LayoutElement(
                x=x0,
                y=y0,
                x2=x1,
                y2=y1,
                content=content,
                source="ocr",
                confidence=confidence,
            )
        ]

    def _extract_full_page_with_ocr(
        self,
        page: fitz.Page,
    ) -> list[LayoutElement]:
        # 2배 크기로 렌더링해 작은 글자의 OCR 정확도를 높인다.
        scale = 2.0
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            alpha=False,
        )

        image = Image.frombytes(
            "RGB",
            (pixmap.width, pixmap.height),
            pixmap.samples,
        )

        ocr_elements = self._ocr.extract(
            image,
            normalize_orientation=False,
        )

        converted_elements: list[LayoutElement] = []

        for element in ocr_elements:
            # 2배로 렌더링한 이미지의 좌표를 원래 PDF 페이지 좌표로 복원한다.
            converted_elements.append(
                LayoutElement(
                    x=element.x / scale,
                    y=element.y / scale,
                    x2=(element.x2 / scale if element.x2 is not None else None),
                    y2=(element.y2 / scale if element.y2 is not None else None),
                    content=element.content,
                    source="ocr",
                    confidence=element.confidence,
                )
            )

        return converted_elements

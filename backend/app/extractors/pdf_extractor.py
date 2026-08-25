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
from app.models.enums import ExtractMethod, ExtractionStrategy


class PdfExtractor(TextExtractor):
    _LINE_OVERLAP_RATIO = 0.45

    def __init__(self, ocr: OcrExtractor) -> None:
        self._ocr = ocr

    def extract(
        self,
        file_path: str,
        *,
        extraction_strategy: str = ExtractionStrategy.AUTO.value,
    ) -> ExtractResult:
        strategy = ExtractionStrategy(extraction_strategy)
        include_image_ocr = strategy is not ExtractionStrategy.TEXT_ONLY
        page_contents: list[str] = []
        document_page_elements: list[list[LayoutElement]] = []
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
                elements, page_has_text, page_has_ocr = self._extract_page(
                    page,
                    include_image_ocr=include_image_ocr,
                )

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
                elif page_has_ocr:
                    elements = self._order_image_blocks(
                        elements,
                        page_width=float(page.rect.width),
                        page_left=float(page.rect.x0),
                    )

                document_page_elements.append(elements)

                page_content = "\n".join(
                    element.content
                    for element in elements
                    if element.content.strip()
                )

                if page_has_ocr:
                    content_offset = sum(len(content) for content in page_contents) + 2 * len(page_contents)
                    review_pages.append(self._build_review_page(page, elements, len(page_contents) + 1, content_offset))

                page_contents.append(page_content)

        content = "\n\n".join(page_contents)
        text_char_count = sum(
            len(element.content)
            for page in document_page_elements
            for element in page
            if element.source == "text"
        )
        ocr_char_count = sum(
            len(element.content)
            for page in document_page_elements
            for element in page
            if element.source == "ocr"
        )

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
            text_char_count=text_char_count,
            ocr_char_count=ocr_char_count,
            extract_method=extract_method,
            review_pages=tuple(review_pages),
        )

    @staticmethod
    def _build_review_page(page: fitz.Page, elements: list[LayoutElement], page_number: int, content_offset: int) -> ExtractedPage:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        page_width = max(float(page.rect.width), 1.0)
        page_height = max(float(page.rect.height), 1.0)
        review_elements = []
        content_cursor = content_offset
        content_elements = [element for element in elements if element.content.strip()]
        for element in content_elements:
            element_start = content_cursor
            content_cursor += len(element.content) + 1
            if element.source != "ocr":
                continue
            x2 = element.x2 if element.x2 is not None else element.x
            y2 = element.y2 if element.y2 is not None else element.y
            review_elements.append(ExtractedElement(
                x=max(0.0, min(1.0, element.x / page_width)),
                y=max(0.0, min(1.0, element.y / page_height)),
                width=max(0.0, min(1.0, (x2 - element.x) / page_width)),
                height=max(0.0, min(1.0, (y2 - element.y) / page_height)),
                text=element.content, confidence=element.confidence,
                content_start=element_start,
                content_end=element_start + len(element.content),
                element_type=element.element_type,
                element_type_source=element.element_type_source,
                is_paragraph_start=element.is_paragraph_start,
                table_id=element.table_id,
                table_row=element.table_row,
            ))
        return ExtractedPage(page_number, pixmap.width, pixmap.height, pixmap.tobytes("png"), tuple(review_elements))

    def _extract_page(
        self,
        page: fitz.Page,
        *,
        include_image_ocr: bool = True,
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

        if include_image_ocr:
            image_group_id = 0
            for block in blocks:
                if block.get("type") == 1:
                    if self._image_contains_text_layer(block, elements):
                        continue
                    image_elements = self._extract_image_block(
                        block, ocr_group_id=image_group_id
                    )

                    if image_elements:
                        elements.extend(image_elements)
                        has_ocr = True
                        image_group_id += 1

        # 스캔 페이지에 페이지 번호·워터마크 같은 작은 텍스트 레이어만 있어도
        # elements 는 비지 않는다. 페이지 대부분을 차지하는 이미지가 있는데
        # 텍스트 레이어가 충분하지 않다면 전체 페이지 OCR로 본문을 보완한다.
        needs_full_page_ocr = include_image_ocr and not has_ocr and (
            not elements
            or (
                self._has_large_page_image(blocks, page)
                and not self._has_sufficient_text_layer(elements, page)
            )
        )
        if needs_full_page_ocr:
            page_ocr_elements = self._extract_full_page_with_ocr(page)

            if page_ocr_elements:
                elements = self._merge_full_page_ocr(
                    elements,
                    page_ocr_elements,
                )
                has_text = any(element.source == "text" for element in elements)
                has_ocr = True

        return elements, has_text, has_ocr

    @staticmethod
    def _has_large_page_image(
        blocks: list[dict[str, Any]],
        page: fitz.Page,
    ) -> bool:
        page_area = max(float(page.rect.width) * float(page.rect.height), 1.0)
        for block in blocks:
            if block.get("type") != 1:
                continue
            x0, y0, x1, y1 = (
                float(value)
                for value in block.get("bbox", (0, 0, 0, 0))
            )
            image_area = max(x1 - x0, 0.0) * max(y1 - y0, 0.0)
            if image_area / page_area >= 0.50:
                return True
        return False

    @staticmethod
    def _has_sufficient_text_layer(
        elements: list[LayoutElement],
        page: fitz.Page,
    ) -> bool:
        text_elements = [
            element for element in elements if element.source == "text"
        ]
        meaningful_chars = sum(
            character.isalnum()
            for element in text_elements
            for character in element.content
        )
        if meaningful_chars < 24:
            return False

        page_area = max(float(page.rect.width) * float(page.rect.height), 1.0)
        covered_area = sum(
            max(
                (element.x2 if element.x2 is not None else element.x)
                - element.x,
                0.0,
            )
            * max(
                (element.y2 if element.y2 is not None else element.y)
                - element.y,
                0.0,
            )
            for element in text_elements
        )
        return covered_area / page_area >= 0.005

    @classmethod
    def _merge_full_page_ocr(
        cls,
        existing_elements: list[LayoutElement],
        ocr_elements: list[LayoutElement],
    ) -> list[LayoutElement]:
        """전체 OCR과 위치가 겹치는 불완전 텍스트 레이어의 중복을 제거한다."""
        remaining_text = [
            element
            for element in existing_elements
            if element.source != "text"
            or not any(
                cls._boxes_overlap(element, ocr_element)
                for ocr_element in ocr_elements
            )
        ]
        return remaining_text + ocr_elements

    @staticmethod
    def _boxes_overlap(first: LayoutElement, second: LayoutElement) -> bool:
        first_x2 = first.x2 if first.x2 is not None else first.x
        first_y2 = first.y2 if first.y2 is not None else first.y
        second_x2 = second.x2 if second.x2 is not None else second.x
        second_y2 = second.y2 if second.y2 is not None else second.y
        first_center = ((first.x + first_x2) / 2, (first.y + first_y2) / 2)
        second_center = (
            (second.x + second_x2) / 2,
            (second.y + second_y2) / 2,
        )
        return (
            second.x <= first_center[0] <= second_x2
            and second.y <= first_center[1] <= second_y2
        ) or (
            first.x <= second_center[0] <= first_x2
            and first.y <= second_center[1] <= first_y2
        )

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
        image_ocr_elements = [
            element for element in elements if element.source == "ocr"
        ]
        image_ocr_blocks, block_elements = cls._ocr_block_proxies(
            image_ocr_elements
        )
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
            return cls._expand_ocr_block_proxies(merged, block_elements)

        ordered: list[LayoutElement] = []
        for group in groups:
            if group.atomic:
                ordered.extend(
                    cls._expand_ocr_block_proxies(
                        group.elements, block_elements
                    )
                )
            else:
                ordered.extend(cls._merge_text_layer_elements(group.elements))
        return ordered

    @classmethod
    def _order_image_blocks(
        cls,
        elements: list[LayoutElement],
        *,
        page_width: float,
        page_left: float,
    ) -> list[LayoutElement]:
        """이미지 내부 순서는 유지하고 여러 이미지 영역만 페이지에 배치한다."""
        if not elements or all(
            element.ocr_group_id is None for element in elements
        ):
            return elements

        proxies, block_elements = cls._ocr_block_proxies(elements)
        groups = build_reading_groups(
            [], proxies, page_width=page_width, page_left=page_left
        )
        if groups is None:
            proxies.sort(key=lambda element: (element.y, element.x))
            return cls._expand_ocr_block_proxies(proxies, block_elements)

        ordered: list[LayoutElement] = []
        for group in groups:
            ordered.extend(
                cls._expand_ocr_block_proxies(group.elements, block_elements)
            )
        return ordered

    @staticmethod
    def _ocr_block_proxies(
        elements: list[LayoutElement],
    ) -> tuple[list[LayoutElement], dict[int, list[LayoutElement]]]:
        grouped: dict[tuple[str, int], list[LayoutElement]] = {}
        for index, element in enumerate(elements):
            key = (
                ("group", element.ocr_group_id)
                if element.ocr_group_id is not None
                else ("element", index)
            )
            grouped.setdefault(key, []).append(element)

        proxies: list[LayoutElement] = []
        block_elements: dict[int, list[LayoutElement]] = {}
        for block in grouped.values():
            proxy = LayoutElement(
                x=min(element.x for element in block),
                y=min(element.y for element in block),
                x2=max(
                    element.x2 if element.x2 is not None else element.x
                    for element in block
                ),
                y2=max(
                    element.y2 if element.y2 is not None else element.y
                    for element in block
                ),
                content="",
                source="ocr",
            )
            proxies.append(proxy)
            block_elements[id(proxy)] = block
        return proxies, block_elements

    @staticmethod
    def _expand_ocr_block_proxies(
        elements: list[LayoutElement],
        block_elements: dict[int, list[LayoutElement]],
    ) -> list[LayoutElement]:
        expanded: list[LayoutElement] = []
        for element in elements:
            expanded.extend(block_elements.get(id(element), [element]))
        return expanded

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
        *,
        ocr_group_id: int,
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

        content = "\n".join(
            element.content
            for element in ocr_elements
            if element.content.strip()
        )
        recognized_char_count = sum(character.isalnum() for character in content)
        if not content or recognized_char_count < 2:
            return []

        return self._map_image_ocr_elements(
            ocr_elements,
            image_width=image_width,
            image_height=image_height,
            image_bbox=bbox,
            ocr_group_id=ocr_group_id,
        )

    @staticmethod
    def _map_image_ocr_elements(
        ocr_elements: list[LayoutElement],
        *,
        image_width: int,
        image_height: int,
        image_bbox: tuple[float, float, float, float],
        ocr_group_id: int | None = None,
    ) -> list[LayoutElement]:
        """Map image-pixel OCR boxes into the image's PDF page rectangle."""
        x0, y0, x1, y1 = (float(value) for value in image_bbox)
        pdf_width = max(x1 - x0, 0.0)
        pdf_height = max(y1 - y0, 0.0)
        if pdf_width == 0 or pdf_height == 0:
            return []

        scale_x = pdf_width / max(float(image_width), 1.0)
        scale_y = pdf_height / max(float(image_height), 1.0)
        mapped: list[LayoutElement] = []

        for element in ocr_elements:
            text = element.content.strip()
            if not text:
                continue

            element_x2 = element.x2 if element.x2 is not None else element.x
            element_y2 = element.y2 if element.y2 is not None else element.y
            left = max(0.0, min(float(image_width), min(element.x, element_x2)))
            top = max(0.0, min(float(image_height), min(element.y, element_y2)))
            right = max(left, min(float(image_width), max(element.x, element_x2)))
            bottom = max(top, min(float(image_height), max(element.y, element_y2)))

            mapped.append(
                LayoutElement(
                    x=x0 + left * scale_x,
                    y=y0 + top * scale_y,
                    x2=x0 + right * scale_x,
                    y2=y0 + bottom * scale_y,
                    content=text,
                    source="ocr",
                    confidence=element.confidence,
                    element_type=element.element_type,
                    element_type_source=element.element_type_source,
                    is_paragraph_start=element.is_paragraph_start,
                    table_id=element.table_id,
                    table_row=element.table_row,
                    ocr_group_id=ocr_group_id,
                )
            )

        return mapped

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

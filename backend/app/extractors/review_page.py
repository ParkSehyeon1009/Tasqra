from io import BytesIO
from dataclasses import replace

from PIL import Image

from app.extractors.layout import LayoutElement
from app.extractors.protocol import ExtractedElement, ExtractedPage


def mark_review_text(text: str, page_number: int) -> str:
    return f"\ue000OCR_REVIEW_{page_number}_START\ue001{text}\ue000OCR_REVIEW_{page_number}_END\ue001"


def resolve_review_content_ranges(content: str, pages: list[ExtractedPage]) -> tuple[str, list[ExtractedPage]]:
    resolved_pages = []
    for page in pages:
        start_marker = f"\ue000OCR_REVIEW_{page.page_number}_START\ue001"
        end_marker = f"\ue000OCR_REVIEW_{page.page_number}_END\ue001"
        marker_start = content.find(start_marker)
        if marker_start < 0:
            resolved_pages.append(page)
            continue
        content = content[:marker_start] + content[marker_start + len(start_marker):]
        marker_end = content.find(end_marker, marker_start)
        if marker_end < 0:
            resolved_pages.append(page)
            continue
        content = content[:marker_end] + content[marker_end + len(end_marker):]

        cursor = marker_start
        resolved_elements = []
        for element in page.elements:
            element_start = content.find(element.text, cursor, marker_end)
            element_end = element_start + len(element.text) if element_start >= 0 else None
            if element_end is not None:
                cursor = element_end
            resolved_elements.append(replace(element, content_start=element_start if element_start >= 0 else None, content_end=element_end))
        resolved_pages.append(replace(page, elements=tuple(resolved_elements)))
    return content, resolved_pages


def build_image_review_page(image: Image.Image, elements: list[LayoutElement], page_number: int) -> ExtractedPage:
    width, height = image.size
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    normalized = tuple(
        ExtractedElement(
            x=max(0.0, min(1.0, item.x / width)),
            y=max(0.0, min(1.0, item.y / height)),
            width=max(0.0, min(1.0, ((item.x2 if item.x2 is not None else item.x) - item.x) / width)),
            height=max(0.0, min(1.0, ((item.y2 if item.y2 is not None else item.y) - item.y) / height)),
            text=item.content,
            confidence=item.confidence,
            element_type=item.element_type,
            element_type_source=item.element_type_source,
            is_paragraph_start=item.is_paragraph_start,
            table_id=item.table_id,
            table_row=item.table_row,
        )
        for item in elements if item.content.strip()
    )
    return ExtractedPage(page_number, width, height, buffer.getvalue(), normalized, page_kind="EMBEDDED_IMAGE")

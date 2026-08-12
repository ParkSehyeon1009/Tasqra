from io import BytesIO

from PIL import Image

from app.extractors.layout import LayoutElement
from app.extractors.protocol import ExtractedElement, ExtractedPage


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
        )
        for item in elements if item.content.strip()
    )
    return ExtractedPage(page_number, width, height, buffer.getvalue(), normalized, page_kind="EMBEDDED_IMAGE")

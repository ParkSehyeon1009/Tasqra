from app.extractors.protocol import ExtractedElement, ExtractedPage
from app.extractors.review_page import mark_review_text, resolve_review_content_ranges


def element(text: str) -> ExtractedElement:
    return ExtractedElement(x=0, y=0, width=1, height=1, text=text)


def test_markers_resolve_exact_ocr_range_when_native_text_is_identical():
    page = ExtractedPage(1, 100, 100, b"image", (element("same"),), page_kind="EMBEDDED_IMAGE")
    marked = "native same\n" + mark_review_text("same", 1)

    content, pages = resolve_review_content_ranges(marked, [page])

    assert content == "native same\nsame"
    assert pages[0].elements[0].content_start == 12
    assert pages[0].elements[0].content_end == 16


def test_markers_resolve_each_line_inside_an_ocr_block():
    page = ExtractedPage(1, 100, 100, b"image", (element("first"), element("second")), page_kind="EMBEDDED_IMAGE")

    content, pages = resolve_review_content_ranges(mark_review_text("first\nsecond", 1), [page])

    assert content == "first\nsecond"
    assert [(item.content_start, item.content_end) for item in pages[0].elements] == [(0, 5), (6, 12)]

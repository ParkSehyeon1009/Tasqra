from app.extractors.layout import LayoutElement
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.reading_order import build_reading_groups


def line(text: str, x: float, y: float, width: float = 160) -> LayoutElement:
    return LayoutElement(
        x=x,
        y=y,
        x2=x + width,
        y2=y + 20,
        content=text,
        source="ocr",
    )


def group_texts(elements: list[LayoutElement]) -> list[str]:
    groups = build_reading_groups(elements, [], page_width=1000)
    assert groups is not None
    return [element.content for group in groups for element in group.elements]


def test_short_two_column_document_is_read_column_first():
    elements = [
        line("왼쪽 1", 80, 100),
        line("오른쪽 1", 600, 100),
        line("왼쪽 2", 80, 150),
        line("오른쪽 2", 600, 150),
    ]

    assert group_texts(elements) == [
        "왼쪽 1",
        "왼쪽 2",
        "오른쪽 1",
        "오른쪽 2",
    ]


def test_full_width_heading_above_short_columns_keeps_region_order():
    elements = [
        line("전체 제목", 80, 30, width=840),
        line("왼쪽 1", 80, 120),
        line("오른쪽 1", 600, 120),
        line("왼쪽 2", 80, 170),
        line("오른쪽 2", 600, 170),
    ]

    assert group_texts(elements) == [
        "전체 제목",
        "왼쪽 1",
        "왼쪽 2",
        "오른쪽 1",
        "오른쪽 2",
    ]


def test_distant_same_height_elements_are_not_merged_into_one_line():
    elements = [line("왼쪽", 50, 100, width=100), line("오른쪽", 700, 100, width=100)]

    merged = OcrExtractor._merge_same_line_elements(elements)

    assert [element.content for element in merged] == ["왼쪽", "오른쪽"]


def test_nearby_same_height_fragments_are_still_merged():
    elements = [line("계약", 50, 100, width=50), line("내용", 115, 100, width=50)]

    merged = OcrExtractor._merge_same_line_elements(elements)

    assert [element.content for element in merged] == ["계약 내용"]

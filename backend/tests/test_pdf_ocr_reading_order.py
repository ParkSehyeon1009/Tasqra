import pytest

from app.extractors.layout import LayoutElement
from app.extractors.pdf_extractor import PdfExtractor


def ocr_line(text: str, x: float, y: float) -> LayoutElement:
    return LayoutElement(
        x=x,
        y=y,
        x2=x + 80,
        y2=y + 20,
        content=text,
        source="ocr",
        confidence=0.99,
    )


def test_mapping_embedded_image_preserves_ocr_reading_order():
    # OCR은 2단 문서를 왼쪽 열 전체 -> 오른쪽 열 전체 순서로 반환한다.
    elements = [
        ocr_line("왼쪽 1", 100, 100),
        ocr_line("왼쪽 2", 100, 200),
        ocr_line("오른쪽 1", 600, 100),
        ocr_line("오른쪽 2", 600, 200),
    ]

    mapped = PdfExtractor._map_image_ocr_elements(
        elements,
        image_width=1000,
        image_height=1000,
        image_bbox=(50, 100, 550, 600),
    )

    assert [element.content for element in mapped] == [
        "왼쪽 1",
        "왼쪽 2",
        "오른쪽 1",
        "오른쪽 2",
    ]


def test_mapping_embedded_image_scales_coordinates_to_pdf_rectangle():
    mapped = PdfExtractor._map_image_ocr_elements(
        [ocr_line("본문", 100, 200)],
        image_width=1000,
        image_height=1000,
        image_bbox=(50, 100, 550, 600),
    )

    assert len(mapped) == 1
    assert mapped[0].x == pytest.approx(100)
    assert mapped[0].y == pytest.approx(200)
    assert mapped[0].x2 == pytest.approx(140)
    assert mapped[0].y2 == pytest.approx(210)


def test_mapping_each_image_block_keeps_its_internal_order():
    first_block = [
        ocr_line("첫 이미지 왼쪽", 50, 100),
        ocr_line("첫 이미지 오른쪽", 500, 50),
    ]
    second_block = [
        ocr_line("둘째 이미지 위", 50, 50),
        ocr_line("둘째 이미지 아래", 50, 150),
    ]

    first_mapped = PdfExtractor._map_image_ocr_elements(
        first_block,
        image_width=1000,
        image_height=1000,
        image_bbox=(0, 0, 500, 500),
    )
    second_mapped = PdfExtractor._map_image_ocr_elements(
        second_block,
        image_width=1000,
        image_height=1000,
        image_bbox=(0, 500, 500, 1000),
    )

    assert [element.content for element in first_mapped] == [
        "첫 이미지 왼쪽",
        "첫 이미지 오른쪽",
    ]
    assert [element.content for element in second_mapped] == [
        "둘째 이미지 위",
        "둘째 이미지 아래",
    ]


def test_hybrid_ordering_does_not_split_an_image_block():
    text_elements = [
        LayoutElement(
            x=50,
            y=index * 30,
            x2=450,
            y2=index * 30 + 20,
            content=f"텍스트 {index}",
            source="text",
        )
        for index in range(6)
    ]
    image_elements = PdfExtractor._map_image_ocr_elements(
        [
            ocr_line("이미지 왼쪽 1", 100, 100),
            ocr_line("이미지 왼쪽 2", 100, 200),
            ocr_line("이미지 오른쪽 1", 600, 100),
            ocr_line("이미지 오른쪽 2", 600, 200),
        ],
        image_width=1000,
        image_height=1000,
        image_bbox=(0, 300, 500, 800),
        ocr_group_id=1,
    )

    ordered = PdfExtractor._order_hybrid_elements(
        text_elements + image_elements,
        page_width=500,
        page_left=0,
    )

    assert [element.content for element in ordered if element.source == "ocr"] == [
        "이미지 왼쪽 1",
        "이미지 왼쪽 2",
        "이미지 오른쪽 1",
        "이미지 오른쪽 2",
    ]


def test_multiple_image_blocks_are_positioned_without_mixing_their_lines():
    lower_block = PdfExtractor._map_image_ocr_elements(
        [
            ocr_line("아래 이미지 왼쪽", 100, 200),
            ocr_line("아래 이미지 오른쪽", 600, 100),
        ],
        image_width=1000,
        image_height=1000,
        image_bbox=(0, 500, 500, 1000),
        ocr_group_id=1,
    )
    upper_block = PdfExtractor._map_image_ocr_elements(
        [
            ocr_line("위 이미지 첫 줄", 100, 100),
            ocr_line("위 이미지 둘째 줄", 100, 200),
        ],
        image_width=1000,
        image_height=1000,
        image_bbox=(0, 0, 500, 500),
        ocr_group_id=2,
    )

    ordered = PdfExtractor._order_image_blocks(
        lower_block + upper_block,
        page_width=500,
        page_left=0,
    )

    assert [element.content for element in ordered] == [
        "위 이미지 첫 줄",
        "위 이미지 둘째 줄",
        "아래 이미지 왼쪽",
        "아래 이미지 오른쪽",
    ]

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


def test_receipt_key_value_block_is_paired_before_column_detection():
    elements = [
        line("과세물품:", 80, 100, width=180),
        line("15,819", 760, 100, width=120),
        line("부가세(VAT):", 80, 140, width=220),
        line("1,581", 780, 140, width=100),
        line("합계:", 80, 180, width=120),
        line("17,400", 760, 180, width=120),
        line("신용카드지불:", 80, 220, width=260),
        line("17,400", 760, 220, width=120),
        line("고객:", 80, 260, width=100),
        line("나인*()", 750, 260, width=130),
        line("받은포인트:", 80, 300, width=220),
        line("87", 840, 300, width=40),
        line("적립포인트:", 80, 340, width=220),
        line("2,256", 780, 340, width=100),
    ]

    merged = OcrExtractor._merge_in_reading_order(elements, [], page_width=1000)

    assert [element.content for element in merged] == [
        "과세물품: 15,819",
        "부가세(VAT): 1,581",
        "합계: 17,400",
        "신용카드지불: 17,400",
        "고객: 나인*()",
        "받은포인트: 87",
        "적립포인트: 2,256",
    ]


def test_distant_colon_heading_and_sentence_remain_separate_columns():
    elements = [
        line("안내:", 50, 100, width=100),
        line("오른쪽 열의 긴 설명 문장입니다", 650, 100, width=300),
    ]

    merged = OcrExtractor._merge_same_line_elements(elements)

    assert [element.content for element in merged] == [
        "안내:",
        "오른쪽 열의 긴 설명 문장입니다",
    ]


def test_true_two_column_paragraphs_keep_column_first_order():
    elements = [
        line("요약:", 60, 100, width=120),
        line("왼쪽 본문 첫째 줄", 60, 140, width=260),
        line("왼쪽 본문 둘째 줄", 60, 180, width=260),
        line("참고:", 580, 100, width=120),
        line("오른쪽 본문 첫째 줄", 580, 140, width=280),
        line("오른쪽 본문 둘째 줄", 580, 180, width=280),
    ]

    ordered = OcrExtractor._merge_in_reading_order(elements, [], page_width=1000)

    assert [element.content for element in ordered] == [
        "요약:",
        "왼쪽 본문 첫째 줄",
        "왼쪽 본문 둘째 줄",
        "참고:",
        "오른쪽 본문 첫째 줄",
        "오른쪽 본문 둘째 줄",
    ]

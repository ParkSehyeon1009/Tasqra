from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.document_service import DocumentService


def element(element_id, text, x, y, start, order):
    return SimpleNamespace(
        id=element_id,
        page_id=1,
        text=text,
        x=x,
        y=y,
        width=0.2,
        height=0.05,
        reading_order=order,
        element_type="TEXT_LINE",
        table_id=None,
        table_row=None,
        is_deleted=False,
        is_in_content=True,
        content_start=start,
        content_end=start + len(text),
    )


def test_added_box_is_inserted_by_coordinates_in_text_and_reading_order():
    a = element(1, "A", 0.1, 0.1, 0, 0)
    b = element(2, "BB", 0.1, 0.3, 2, 1)
    c = element(3, "CCC", 0.1, 0.4, 5, 2)
    d = element(4, "DDDD", 0.1, 0.2, 9, 3)
    page = SimpleNamespace(id=1, page_number=1, elements=[a, b, c, d])
    extracted = SimpleNamespace(content="A\nBB\nCCC\nDDDD", char_count=13)
    document = SimpleNamespace(review_pages=[page], extracted_text=extracted)
    service = DocumentService(MagicMock(), MagicMock(), MagicMock())

    changed = service._reorder_page_ocr_content(document, page)

    assert changed is True
    assert extracted.content == "A\nDDDD\nBB\nCCC"
    assert [(item.text, item.reading_order) for item in (a, d, b, c)] == [
        ("A", 0),
        ("DDDD", 1),
        ("BB", 2),
        ("CCC", 3),
    ]
    for item in (a, b, c, d):
        assert extracted.content[item.content_start:item.content_end] == item.text


def test_new_box_content_is_inserted_before_following_page_content():
    a = element(1, "A", 0.1, 0.1, 0, 0)
    b = element(2, "B", 0.1, 0.3, 2, 1)
    added = element(3, "D", 0.1, 0.2, 0, 2)
    added.content_start = None
    added.content_end = None
    added.is_in_content = False
    next_page_element = element(4, "NEXT", 0.1, 0.1, 4, 0)
    next_page_element.page_id = 2
    page = SimpleNamespace(id=1, page_number=1, elements=[a, b, added])
    next_page = SimpleNamespace(id=2, page_number=2, elements=[next_page_element])
    extracted = SimpleNamespace(content="A\nB\nNEXT", char_count=8)
    document = SimpleNamespace(review_pages=[page, next_page], extracted_text=extracted)
    service = DocumentService(MagicMock(), MagicMock(), MagicMock())

    service._insert_page_ocr_content(document, page, added)
    service._reorder_page_ocr_content(document, page)

    assert extracted.content == "A\nD\nB\nNEXT"
    assert next_page_element.content_start == 6
    assert extracted.content[next_page_element.content_start:next_page_element.content_end] == "NEXT"


def test_two_column_page_is_read_down_each_column():
    left_top = element(1, "L1", 0.1, 0.1, 0, 0)
    left_added = element(2, "LD", 0.1, 0.2, 0, 4)
    left_bottom = element(3, "L2", 0.1, 0.3, 0, 1)
    right_top = element(4, "R1", 0.7, 0.1, 0, 2)
    right_bottom = element(5, "R2", 0.7, 0.3, 0, 3)

    ordered = DocumentService._coordinate_order([
        left_top, right_top, left_bottom, right_bottom, left_added,
    ])

    assert [item.text for item in ordered] == ["L1", "LD", "L2", "R1", "R2"]


def test_table_rows_stay_together_between_surrounding_paragraphs():
    before = element(1, "BEFORE", 0.1, 0.05, 0, 0)
    header = element(2, "HEADER", 0.1, 0.2, 0, 1)
    header.element_type = "TABLE_HEADER"
    header.table_id = 7
    header.table_row = 0
    row = element(3, "ROW", 0.1, 0.3, 0, 2)
    row.element_type = "TABLE_ROW"
    row.table_id = 7
    row.table_row = 1
    after = element(4, "AFTER", 0.1, 0.6, 0, 3)

    ordered = DocumentService._coordinate_order([row, after, before, header])

    assert [item.text for item in ordered] == ["BEFORE", "HEADER", "ROW", "AFTER"]

from app.extractors.layout import LayoutElement
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.table_detector import TableCell
from app.schemas.document import OcrElementResponse


def test_table_rows_keep_structure_metadata():
    header = TableCell(table_id=4, row=0, column=0, x1=0, y1=0, x2=50, y2=10)
    body = TableCell(table_id=4, row=1, column=0, x1=0, y1=10, x2=50, y2=20)
    cell_elements = {
        header: [LayoutElement(x=1, y=1, x2=10, y2=8, content="제목", source="ocr")],
        body: [LayoutElement(x=1, y=11, x2=10, y2=18, content="내용", source="ocr")],
    }

    rows = OcrExtractor._build_table_rows([header, body], cell_elements, offset_x=0, offset_y=0)

    assert [(row.element_type, row.table_id, row.table_row) for row in rows] == [
        ("TABLE_HEADER", 4, 0),
        ("TABLE_ROW", 4, 1),
    ]


def test_ocr_response_exposes_chunking_metadata():
    response = OcrElementResponse.model_validate({
        "id": 1,
        "original_text": "원문",
        "text": "수정문",
        "x": 0.1,
        "y": 0.2,
        "width": 0.3,
        "height": 0.1,
        "confidence": 0.9,
        "source": "OCR",
        "element_type": "HEADING",
        "element_type_source": "AUTO",
        "is_paragraph_start": True,
        "table_id": None,
        "table_row": None,
        "reading_order": 0,
        "version": 1,
        "is_excluded": False,
        "content_start": 0,
        "content_end": 3,
        "is_in_content": True,
    })

    assert response.element_type == "HEADING"
    assert response.is_paragraph_start is True
    assert response.content_end == 3

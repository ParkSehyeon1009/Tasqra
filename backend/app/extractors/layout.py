from dataclasses import dataclass

@dataclass
class LayoutElement:
    x: float
    y: float
    content: str
    source: str      # "text" | "ocr"
    confidence: float | None = None
    x2: float | None = None
    y2: float | None = None
    element_type: str = "TEXT_LINE"
    element_type_source: str = "AUTO"
    is_paragraph_start: bool = False
    table_id: int | None = None
    table_row: int | None = None
    # PDF 안의 같은 이미지에서 나온 OCR 요소를 페이지 배치 시 한 영역으로 다룬다.
    ocr_group_id: int | None = None

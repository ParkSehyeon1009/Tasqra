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

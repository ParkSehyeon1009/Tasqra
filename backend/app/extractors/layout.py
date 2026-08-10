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

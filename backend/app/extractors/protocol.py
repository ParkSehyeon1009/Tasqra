# =============================================================================
# 이 파일의 책임: 문서에서 텍스트를 뽑아내는 모든 추출기가 만족해야 할
#   "계약(Protocol)"을 정의한다. 실제 구현(PDF/DOCX/HWPX/OCR)은 이 Protocol에
#   의존하지 않고 시그니처만 맞추면 된다 (구조적 타이핑).
# 다른 파일과의 관계: fake_extractor.py가 이 Protocol을 구현하는 참고 예시다.
#   registry.py가 file_type -> TextExtractor 매핑을 관리하고, 실제 pdf/docx/
#   hwpx/ocr extractor(담당자 A가 구현)도 이 Protocol을 구현해 registry에 등록된다.
# Spring 비교: Java interface(TextExtractor)와 동일. §5 설계상 텍스트 추출은
#   PyMuPDF/python-docx 등 동기 라이브러리로 하고, 업로드 라우터 자체도 동기(def)로
#   두어 FastAPI가 threadpool에서 실행하므로 extract()도 동기 메서드로 정의한다
#   (AIClientProtocol.generate만 async인 것과 대조된다).
# =============================================================================

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExtractResult:
    content: str
    page_count: int
    char_count: int
    extract_method: str


class TextExtractor(Protocol):
    def extract(self, file_path: str) -> ExtractResult:
        ...

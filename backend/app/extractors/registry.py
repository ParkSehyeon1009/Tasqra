# =============================================================================
# 이 파일의 책임: 파일 확장자(file_type) 문자열을 실제 TextExtractor 구현체에
#   연결해주는 레지스트리. "새 구현체를 register()로 추가하기만 하면 확장되고
#   기존 코드는 수정되지 않는다"는 §2-3 원칙을 위한 장치다.
# 다른 파일과의 관계: dependencies.py의 get_extractor_registry()가 이 클래스를
#   생성하고 FakeExtractor(및 담당자 A가 만들 pdf/docx/hwpx/ocr extractor)를
#   register()로 채운다. 업로드 서비스(extraction_service.py, 담당자 A)가
#   get(file_type)으로 알맞은 추출기를 꺼내 쓴다.
# Spring 비교: Java의 Map<String, TextExtractor> 빈 컬렉션을 주입받아 확장자별로
#   분기하는 전략 패턴(Strategy Pattern)과 동일한 목적.
# =============================================================================

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.extractors.protocol import TextExtractor


class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: dict[str, TextExtractor] = {}

    def register(self, file_type: str, extractor: TextExtractor) -> None:
        self._extractors[file_type.lower()] = extractor

    def get(self, file_type: str) -> TextExtractor:
        extractor = self._extractors.get(file_type.lower())
        if extractor is None:
            raise BusinessError(
                ErrorCode.INVALID_FILE_TYPE, detail=f"file_type={file_type}"
            )
        return extractor

# =============================================================================
# 이 파일의 책임: protocol.py의 TextExtractor를 구현하되, 실제 파일을 파싱하지
#   않고 고정된 값을 반환하는 테스트/개발용 추출기.
# 다른 파일과의 관계: dependencies.py의 get_extractor_registry()가 참고/기본
#   구현체로 등록한다. pdf_extractor.py 등 실제 구현체(담당자 A)를 만들 때
#   참고할 최소 예시이기도 하다.
# Spring 비교: ai/fake_client.py의 FakeAIClient와 같은 성격의 Fake 구현체.
# =============================================================================

from app.extractors.protocol import ExtractResult, TextExtractor


class FakeExtractor(TextExtractor):
    def extract(self, file_path: str) -> ExtractResult:
        content = f"fake_extracted_text_for : {file_path}"
        return ExtractResult(
            content=content,
            page_count=1,
            char_count=len(content),
            extract_method="FAKE",
        )

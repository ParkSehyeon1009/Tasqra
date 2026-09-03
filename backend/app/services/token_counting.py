# =============================================================================
# 이 파일의 책임: 생성 모델 프롬프트 예산 계산에 쓸 토큰 계산 계약과 보수적
#   fallback 구현을 제공한다.
# 다른 파일과의 관계: chat_service.py와 context_assembly.py가 같은 counter를
#   주입받아 질문·시스템 지시문·근거를 한 단위로 계산한다.
# Spring 비교: TokenCounter 인터페이스의 기본 @Bean 구현에 해당한다. 실제 모델
#   tokenizer Bean이 생기면 이 구현 대신 주입하면 된다.
# =============================================================================


class Utf8ByteTokenCounter:
    """UTF-8 바이트 수를 세는 보수적 근사 계산기.

    실제 tokenizer가 아니다. 현재 LLM provider가 tokenizer를 노출하지 않으므로
    한글 1글자를 보통 3으로 세어 여유를 크게 잡는다. 모델에 맞는 정확 counter가
    준비되면 동일한 ``count(text)`` 계약으로 교체한다.
    """

    is_exact = False
    name = "utf8-byte-conservative"

    def count(self, text: str) -> int:
        return len(text.encode("utf-8"))

# =============================================================================
# 이 파일의 책임: client_protocol.py의 AIClientProtocol을 실제 OpenAI API 호출로
#   구현한다.
# 다른 파일과의 관계: core/config.py의 settings.API_KEY/AI_MODEL을 사용한다.
#   서비스 레이어는 이 클래스를 직접 참조하지 않고 client_protocol.AIClientProtocol
#   타입으로만 의존한다 (DI를 통해 FakeAIClient <-> OpenAIClient를 교체 가능하게 하기 위함).
#   타임아웃/예외 래핑은 이 클래스가 아니라 analyzers/*.py에서 asyncio.wait_for +
#   BusinessError로 처리하므로 여기서는 순수하게 API 호출 결과만 반환한다.
# Spring 비교: interface AIClient의 실제 프로덕션 구현체(@Component/@Service)에 해당.
#   application.yml의 api-key 값을 생성자 주입받는 것과 동일하게, 여기서는
#   Settings(=config.py)를 생성자 인자로 받는다.
# =============================================================================

import time

from openai import AsyncOpenAI

from app.ai.client_protocol import AIClientProtocol, AIResult
from app.core.config import Settings


class OpenAIClient(AIClientProtocol):
    provider = "openai"

    def __init__(self, settings: Settings) -> None:
        self._model = settings.AI_MODEL
        self._client = AsyncOpenAI(api_key=settings.API_KEY)

    async def generate(self, prompt: str) -> str:
        result = await self.generate_with_meta(prompt)
        return result.text

    async def generate_with_meta(self, prompt: str) -> AIResult:
        start = time.perf_counter()
        # prompts.py가 "JSON으로 응답" 하도록 지시하므로, JSON 모드로 형식 이탈을 방지한다.
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return AIResult(
            text=response.choices[0].message.content,
            model_name=response.model,
            tokens_in=response.usage.prompt_tokens if response.usage else None,
            tokens_out=response.usage.completion_tokens if response.usage else None,
            latency_ms=elapsed_ms,
        )


# =============================================================================
# 이 파일의 책임: client_protocol.py의 AIClientProtocol을, Ollama처럼
#   "OpenAI 호환(OpenAI-compatible)" API를 제공하는 로컬 LLM 서버 호출로 구현한다.
# 다른 파일과의 관계: openai_client.py와 구조가 거의 같고, 차이는 AsyncOpenAI에
#   base_url을 지정한다는 점뿐이다 — 로컬 서버가 /v1/chat/completions 스펙을
#   그대로 따르므로 SDK와 호출 코드를 재사용할 수 있다.
#   dependencies.get_ai_client()가 settings.AI_PROVIDER == "local"일 때 주입한다.
# 주의: Ollama의 기본 컨텍스트 창(num_ctx)은 2048 토큰으로 좁다. 긴 문서를 그대로
#   보내면 에러 없이 앞부분만 읽고 나머지를 버리므로, 분석기에서
#   settings.AI_MAX_INPUT_CHARS로 미리 잘라서 보낸다 (analyzers/prompts.py).
# =============================================================================

import time

from openai import AsyncOpenAI

from app.ai.client_protocol import AIClientProtocol, AIResult
from app.core.config import Settings


class LocalAIClient(AIClientProtocol):
    provider = "local"

    def __init__(self, settings: Settings) -> None:
        self._model = settings.AI_MODEL
        self._client = AsyncOpenAI(
            base_url=settings.AI_BASE_URL,
            # 로컬 서버는 인증을 하지 않지만 OpenAI SDK는 api_key가 비어 있으면
            # 클라이언트를 만들지 못하므로 자리표시자 값을 넣는다.
            api_key=settings.API_KEY or "local",
        )

    async def generate(self, prompt: str) -> str:
        result = await self.generate_with_meta(prompt)
        return result.text

    async def generate_with_meta(self, prompt: str) -> AIResult:
        start = time.perf_counter()
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            # prompts.py가 JSON 응답을 지시하므로 형식 이탈을 막는다.
            response_format={"type": "json_object"},
            # 분류/요약은 매번 같은 답이 나오는 편이 검증에 유리하다.
            temperature=0,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return AIResult(
            text=response.choices[0].message.content or "",
            model_name=response.model,
            tokens_in=response.usage.prompt_tokens if response.usage else None,
            tokens_out=response.usage.completion_tokens if response.usage else None,
            latency_ms=elapsed_ms,
        )

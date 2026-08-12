# =============================================================================
# 이 파일의 책임: client_protocol.py의 AIClientProtocol을 구현하되,
#   실제 외부 API를 호출하지 않고 고정된 값을 반환하는 테스트/개발용 클라이언트.
# 다른 파일과의 관계: 테스트 코드나 로컬 개발 시 Depends()의 override 대상으로 쓰인다.
#   예: app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
#   dependencies.py에서 settings.USE_FAKE_AI가 true일 때 기본으로 주입되는 구현체.
# Spring 비교: 테스트에서 실제 Bean 대신 등록하는 Stub/Fake 구현체
#   (@Primary 없이 테스트 컨텍스트에서 @TestConfiguration으로 갈아끼우는 것과 유사).
#   Mockito의 Mock과 다르게, Fake는 실제 동작하는 최소 구현체라는 점이 특징입니다.
# =============================================================================

import asyncio
import time

from app.ai.client_protocol import AIClientProtocol, AIResult

FAKE_MODEL_NAME = "fake-model"
FAKE_DELAY_SECONDS = 0.1


class FakeAIClient(AIClientProtocol):
    provider = "fake"

    async def generate(self, prompt: str) -> str:
        result = await self.generate_with_meta(prompt)
        return result.text

    async def generate_with_meta(self, prompt: str) -> AIResult:
        start = time.perf_counter()
        await asyncio.sleep(FAKE_DELAY_SECONDS)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return AIResult(
            text=f"fake_response_for : {prompt}",
            model_name=FAKE_MODEL_NAME,
            tokens_in=len(prompt.split()),
            tokens_out=10,
            latency_ms=elapsed_ms,
        )

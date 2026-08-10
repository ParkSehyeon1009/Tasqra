import asyncio
import json

from app.ai.client_protocol import AIClientProtocol
from app.ai.fake_client import FakeAIClient
from app.analyzers.prompts import CATEGORY_CANDIDATES, PROMPT_VERSION, build_category_prompt
from app.analyzers.protocol import Analyzer, AnalyzeResult
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError

FALLBACK_CATEGORY = "기타"


class CategoryAnalyzer(Analyzer):
    def __init__(self, ai_client: AIClientProtocol) -> None:
        self._ai_client = ai_client

    async def analyze(self, text: str) -> AnalyzeResult:
        prompt = build_category_prompt(text)

        try:
            ai_result = await asyncio.wait_for(
                self._ai_client.generate_with_meta(prompt),
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise BusinessError(ErrorCode.AI_TIMEOUT) from exc
        except Exception as exc:
            raise BusinessError(ErrorCode.AI_PROVIDER_ERROR) from exc

        try:
            parsed = json.loads(ai_result.text)
            category = parsed["category"]
            reason = parsed.get("reason", "")
        except (json.JSONDecodeError, KeyError):
            category = FALLBACK_CATEGORY
            reason = ai_result.text

        # LLM이 후보 목록 밖의 값을 반환해도 담당자 C의 category 필터/검색이
        # 깨지지 않도록 여기서 한 번 더 방어한다.
        if category not in CATEGORY_CANDIDATES:
            category = FALLBACK_CATEGORY

        provider = "fake" if isinstance(self._ai_client, FakeAIClient) else "openai"

        return AnalyzeResult(
            result={"category": category, "reason": reason},
            provider=provider,
            model_name=ai_result.model_name,
            prompt_version=PROMPT_VERSION,
            tokens_in=ai_result.tokens_in,
            tokens_out=ai_result.tokens_out,
            latency_ms=ai_result.latency_ms,
        )

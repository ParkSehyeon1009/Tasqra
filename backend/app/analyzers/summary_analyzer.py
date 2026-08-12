import asyncio
import json

from app.ai.client_protocol import AIClientProtocol
from app.analyzers.prompts import (
    PROMPT_VERSION,
    build_summary_prompt,
    truncate_for_prompt,
)
from app.analyzers.protocol import Analyzer, AnalyzeResult
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError

#Analyzer 상속
class SummaryAnalyzer(Analyzer):
    #생성자 선언
    def __init__(self, ai_client: AIClientProtocol) -> None:
        self._ai_client = ai_client

    async def analyze(self, text: str) -> AnalyzeResult:
        prompt = build_summary_prompt(
            truncate_for_prompt(text, settings.AI_MAX_INPUT_CHARS)
        )

        try:
            # settings.AI_TIMEOUT_SECONDS를 넘기면 asyncio.TimeoutError 발생
            ai_result = await asyncio.wait_for(
                self._ai_client.generate_with_meta(prompt),
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise BusinessError(ErrorCode.AI_TIMEOUT) from exc
        except Exception as exc:
            raise BusinessError(ErrorCode.AI_PROVIDER_ERROR) from exc

        # AI가 JSON으로 답하도록 프롬프트에서 지시했지만, 형식이 깨져서 와도
        # 서버가 죽지 않도록 방어적으로 파싱한다.
        try:
            parsed = json.loads(ai_result.text)
            summary_text = parsed["summary"]
        except (json.JSONDecodeError, KeyError):
            summary_text = ai_result.text

        # 클라이언트가 자기 라벨을 들고 있으므로("fake"/"openai"/"local")
        # 구현체를 isinstance로 판별하지 않고 그대로 기록한다.
        provider = self._ai_client.provider

        return AnalyzeResult(
            result={"summary": summary_text},
            provider=provider,
            model_name=ai_result.model_name,
            prompt_version=PROMPT_VERSION,
            tokens_in=ai_result.tokens_in,
            tokens_out=ai_result.tokens_out,
            latency_ms=ai_result.latency_ms,
        )
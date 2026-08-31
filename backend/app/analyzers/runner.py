"""호출 단위 재시도·검증·메타 집계. 성공한 앞 구간을 다시 호출하지 않는다."""
import asyncio
import logging
import time
from collections.abc import Callable

from pydantic import ValidationError

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)
Progress = Callable[[str, int, int], None]


class Runner:
    def __init__(self, client, settings, budget, progress: Progress | None = None):
        self.client, self.settings, self.budget = client, settings, budget
        self.progress = progress or (lambda stage, done, total: None)
        self.responses = []
        self.calls = 0
        self.started = time.monotonic()

    async def call(self, prompt, schema, *, validate=None, stage="분석"):
        prompt = self.budget.prepare(prompt)
        for attempt in range(self.settings.AI_CHUNK_RETRIES + 1):
            self.calls += 1
            try:
                result = await asyncio.wait_for(self.client.generate_with_meta(prompt), self.settings.AI_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                code = ErrorCode.AI_TIMEOUT
            except Exception:
                logger.warning("AI 호출 실패 stage=%s attempt=%s", stage, attempt + 1, exc_info=True)
                code = ErrorCode.AI_PROVIDER_ERROR
            else:
                self.responses.append(result)
                try:
                    parsed = schema.model_validate_json(result.text)
                    if validate:
                        validate(parsed)
                    return parsed
                except (ValidationError, ValueError, TypeError):
                    # 원문 응답이나 문서 본문은 로그에 노출하지 않는다.
                    logger.warning("AI 응답 검증 실패 stage=%s attempt=%s", stage, attempt + 1)
                    code = ErrorCode.AI_INVALID_RESPONSE
            if attempt < self.settings.AI_CHUNK_RETRIES:
                self.progress(f"{stage} 재시도", attempt + 1, self.settings.AI_CHUNK_RETRIES)
        raise BusinessError(code, f"{stage} 처리에 실패했습니다. 일부 구간을 제외한 결과는 저장하지 않았습니다.")

    def metadata(self):
        def total(attr):
            values = [getattr(r, attr) for r in self.responses]
            # 응답을 못 받은 호출의 사용량은 알 수 없으므로 부분합을 총량으로 표시하지 않는다.
            return sum(values) if len(values) == self.calls and all(v is not None for v in values) else None
        return {"model_name": self.responses[-1].model_name,
                "tokens_in": total("tokens_in"), "tokens_out": total("tokens_out"),
                "latency_ms": int((time.monotonic() - self.started) * 1000)}

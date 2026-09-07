"""호출 단위 재시도·검증·메타 집계. 성공한 앞 구간을 다시 호출하지 않는다."""
# ① 책임: AI 호출의 timeout·재시도·응답 검증과 호출 메타데이터 집계를 담당한다.
# ② 관계: 모든 analyzer가 AI client를 직접 다루지 않고 이 공통 실행 경계를 사용한다.
# ③ Spring 비교: RetryTemplate과 Bean Validation을 묶은 공통 gateway adapter에 해당한다.

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import replace

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

    async def call(self, prompt, schema, *, parser=None, validate=None, stage="분석"):
        # 검증에 쓸 스키마를 호출에도 실어 보낸다. 지원하는 서버는 이것으로
        # 디코딩을 제약하므로, 형식 위반이 «재시도로 걸러내는 것» 에서
        # «애초에 나올 수 없는 것» 으로 바뀐다. 예산 계산에는 영향이 없다
        # (문법 제약이지 프롬프트에 붙는 글자가 아니다).
        # parser가 있으면 서버에는 같은 schema를 보내되 실제 원시 응답 검증은
        # parser에 맡긴다. 금액처럼 정규화 전 엄격한 JSON 경계가 필요한 경우다.
        prompt = self.budget.prepare(replace(prompt, response_schema=schema))
        for attempt in range(self.settings.AI_CHUNK_RETRIES + 1):
            self.calls += 1
            try:
                result = await asyncio.wait_for(self.client.generate_with_meta(prompt), self.settings.AI_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning(
                    "AI 호출 시간 초과 stage=%s attempt=%s timeout_seconds=%s",
                    stage, attempt + 1, self.settings.AI_TIMEOUT_SECONDS)
                code = ErrorCode.AI_TIMEOUT
            except Exception:
                logger.warning("AI 호출 실패 stage=%s attempt=%s", stage, attempt + 1, exc_info=True)
                code = ErrorCode.AI_PROVIDER_ERROR
            else:
                self.responses.append(result)
                try:
                    parsed = parser(result) if parser else schema.model_validate_json(result.text)
                    if validate:
                        validate(parsed)
                    return parsed
                except BusinessError as exc:
                    if exc.error_code is not ErrorCode.AI_INVALID_RESPONSE:
                        raise
                    logger.warning(
                        "AI 응답 검증 실패 stage=%s attempt=%s type=parser detail=invalid_response",
                        stage, attempt + 1)
                    code = ErrorCode.AI_INVALID_RESPONSE
                except (ValidationError, ValueError, TypeError) as exc:
                    # 원문 응답이나 문서 본문은 로그에 노출하지 않는다.
                    if isinstance(exc, ValidationError):
                        detail = ",".join(".".join(str(p) for p in error["loc"])
                                          for error in exc.errors()[:3]) or "schema"
                        failure = "schema"
                    else:
                        detail = str(exc)[:120]
                        failure = "custom"
                    logger.warning(
                        "AI 응답 검증 실패 stage=%s attempt=%s type=%s detail=%s",
                        stage, attempt + 1, failure, detail)
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

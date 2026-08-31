"""입력 예산과 원문 위치를 보존하는 분할. 모델별 실측 토큰 수로 주장하지 않는다."""
import json
from dataclasses import dataclass, replace

from app.ai.client_protocol import AIRequest
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError


def byte_size(text: str) -> int:
    # 로컬 모델 tokenizer를 로드하지 않는 보수적 예산이다. UTF-8 byte 단위
    # 추정 + 메시지 여유를 사용한다. 실제 서버 컨텍스트는 운영자가 맞춰야 한다.
    return len(text.encode("utf-8"))


def encoded_size(value) -> int:
    return byte_size(json.dumps(value, ensure_ascii=False))


class PromptBudget:
    def __init__(self, settings):
        self.context = settings.AI_CONTEXT_TOKENS
        self.output = settings.AI_MAX_OUTPUT_TOKENS
        self.max_chars = settings.AI_MAX_INPUT_CHARS

    def fits(self, prompt: AIRequest) -> bool:
        return byte_size(prompt.system) + byte_size(prompt.user) + self.output + 256 <= self.context

    def prepare(self, prompt: AIRequest) -> AIRequest:
        if not self.fits(prompt):
            raise BusinessError(ErrorCode.AI_INPUT_TOO_LARGE)
        return replace(prompt, max_output_tokens=self.output)


@dataclass(frozen=True)
class TextChunk:
    start: int
    end: int
    text: str
    hard_split: bool = False


def split_document(text: str, budget: PromptBudget, builder, *, overlap: int, max_chunks: int) -> list[TextChunk]:
    """전체 원문을 덮는다. 문단·줄·문장 경계를 우선하고 불가피한 강제 분할을 기록한다."""
    chunks = []
    start = 0
    while start < len(text):
        lo, hi = start, min(len(text), start + budget.max_chars)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if budget.fits(builder(text[start:mid], start, mid)):
                lo = mid
            else:
                hi = mid - 1
        if lo == start:
            raise BusinessError(ErrorCode.AI_INPUT_TOO_LARGE)
        end = lo
        hard = end < len(text)
        if hard:
            # 예산의 절반 이상을 채운 경계만 고려해 아주 작은 조각 반복을 방지한다.
            floor = start + max(1, (end - start) // 2)
            for boundary in ("\n\n", "\n", ". ", "。", "! ", "? "):
                at = text.rfind(boundary, floor, end)
                if at >= floor:
                    end = at + len(boundary)
                    hard = False
                    break
        chunks.append(TextChunk(start, end, text[start:end], hard))
        if len(chunks) > max_chunks:
            raise BusinessError(ErrorCode.AI_INPUT_TOO_LARGE, "분석 가능한 구간 수를 초과했습니다. 문서를 나눠 주세요.")
        if end == len(text):
            break
        # 앞뒤 문맥만 겹친다. 한 글자도 건너뛰지 않고 매번 전진한다.
        start = end - min(overlap, (end - start) // 4)
    return chunks


def sample_input(text: str, budget: PromptBudget, builder) -> tuple[AIRequest, dict]:
    """분류용 앞/중간/뒤 표본. 요약은 이 함수를 쓰지 않는다."""
    def make(n):
        if n >= len(text):
            ranges = [[0, len(text)]]
            sample = text
        else:
            first = n // 2
            middle = n // 4
            last = n - first - middle
            center = (len(text) - middle) // 2
            ranges = [[0, first], [center, center + middle], [len(text) - last, len(text)]]
            sample = "\n[중간 생략]\n".join(text[a:b] for a, b in ranges)
        meta = {"truncated": n < len(text), "original_chars": len(text),
                "included_chars": n, "included_ranges": ranges}
        return builder(sample, **meta), meta

    lo, hi = 0, min(len(text), budget.max_chars)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if budget.fits(make(mid)[0]):
            lo = mid
        else:
            hi = mid - 1
    prompt, meta = make(lo)
    if text and lo == 0:
        raise BusinessError(ErrorCode.AI_INPUT_TOO_LARGE)
    return budget.prepare(prompt), meta

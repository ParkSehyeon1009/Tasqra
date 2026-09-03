import re

from app.analyzers.output_schemas import CategoryOutput
from app.analyzers.prompt_input import PromptBudget, sample_input
from app.analyzers.prompts import CATEGORY_PROMPT_VERSION, build_category_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings


class CategoryAnalyzer:
    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        budget = PromptBudget(self._settings)
        prompt, meta = sample_input(text, budget, build_category_prompt)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        runner.progress("문서 분류", 0, 1)
        parsed = await runner.call(prompt, CategoryOutput, stage="문서 분류")
        category, reason = _validate_category(text, parsed.category, parsed.reason)
        traits = _document_traits(text)
        runner.progress("문서 분류", 1, 1)
        return AnalyzeResult(
            result={"category": category, "reason": reason, "traits": traits,
                    "input_scope": meta, "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=CATEGORY_PROMPT_VERSION,
            **runner.metadata(),
        )


def _validate_category(text: str, category: str, reason: str) -> tuple[str, str]:
    """제목·문서 목적과 명백히 모순되는 단일 분류만 보수적으로 교정한다."""
    compact = re.sub(r"\s+", "", text[:1200])
    if re.search(r"(?:구매|용역|공사)?입찰(?:재)?공고|제안요청서", compact, re.I):
        if category != "RFP":
            return "RFP", "문서 제목과 도입부에 입찰 공고 또는 제안요청서가 명시되어 있음"
    if re.search(r"(?:협력방안|상품공급|사업)제안서", compact) and not re.search(r"입찰(?:재)?공고", compact):
        if category == "ETC":
            return "PROPOSAL", "문서 제목과 도입부의 주된 목적이 협력 또는 상품 공급 제안임"
    if category == "COST_SHEET":
        return "ETC", "산출내역서·견적서·원가계산서는 7종 분류 정책에서 기타로 통합됨"
    return category, reason


def _document_traits(text: str) -> list[str]:
    """주 유형과 별개로 후속 기능에 유용한 복합 성격만 보수적으로 표시한다."""
    compact = re.sub(r"\s+", "", text)
    rules = (
        ("COST_DETAILS", r"산출내역서|원가계산서|견적서|수량\s*단가\s*(?:금액|합계)|공급가액.*부가세"),
        ("SCHEDULE", r"추진일정|사업기간|계약기간|제출기한|접수기간|일정표"),
        ("CONTRACT_TERMS", r"계약조건|계약금액|계약기간|과업내용|지체상금|하자보수"),
        ("DECISION_RECORD", r"의결사항|결정사항|합의사항|승인결과|선정결과"),
        ("ACTION_ITEMS", r"조치사항|후속조치|담당자.*기한|까지\s*(?:제출|보고|완료|회신)"),
    )
    return [name for name, pattern in rules if re.search(pattern, compact, re.I)]

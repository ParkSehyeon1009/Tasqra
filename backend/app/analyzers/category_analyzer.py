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
        runner.progress("문서 분류", 1, 1)
        return AnalyzeResult(
            result={"category": category, "reason": reason,
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
        if category in {"COST_SHEET", "ETC"}:
            return "PROPOSAL", "문서 제목과 도입부의 주된 목적이 협력 또는 상품 공급 제안임"
    if category == "COST_SHEET" and re.search(r"금액(?:의)?\s*(?:언급|기재)?\s*(?:없|없음)", reason):
        return "ETC", "산출내역서 판단과 분류 근거가 모순되어 기타로 보수적으로 교정함"
    return category, reason
import re

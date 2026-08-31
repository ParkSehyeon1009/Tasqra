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
        runner.progress("문서 분류", 1, 1)
        return AnalyzeResult(
            result={**parsed.model_dump(), "input_scope": meta, "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=CATEGORY_PROMPT_VERSION,
            **runner.metadata(),
        )

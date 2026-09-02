from app.analyzers.action_candidate_finder import find_action_candidates
from app.analyzers.output_schemas import ActionSelectionOutput
from app.analyzers.prompt_input import PromptBudget
from app.analyzers.prompts import ACTION_TASK_PROMPT_VERSION, build_action_task_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings
from app.schemas.extraction import TaskSuggestionExtraction


class ActionTaskAnalyzer:
    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        candidates = find_action_candidates(text)
        if not candidates:
            return AnalyzeResult(result={"task_suggestions": [], "candidate_count": 0,
                "selected_count": 0, "call_count": 0}, provider=self._ai_client.provider,
                model_name=self._ai_client.model_name,
                prompt_version=ACTION_TASK_PROMPT_VERSION, latency_ms=0)
        budget = PromptBudget(self._settings)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        groups, group = [], []
        for candidate in candidates:
            next_group = group + [candidate]
            if group and not budget.fits(build_action_task_prompt([c.as_prompt_record() for c in next_group])):
                groups.append(group); group = [candidate]
            else:
                group = next_group
        if group:
            groups.append(group)
        selected_candidates = []
        for index, candidates_group in enumerate(groups):
            allowed = {candidate.id: candidate for candidate in candidates_group}
            def verify(parsed, allowed=allowed):
                if not set(parsed.selected_ids) <= allowed.keys():
                    raise ValueError("unknown action candidate id")
                if len(set(parsed.selected_ids)) != len(parsed.selected_ids):
                    raise ValueError("duplicated action candidate id")
            stage = f"액션 태스크 선별 {index+1}/{len(groups)}"
            parsed = await runner.call(build_action_task_prompt(
                [c.as_prompt_record() for c in candidates_group]), ActionSelectionOutput,
                validate=verify, stage=stage)
            for candidate_id in parsed.selected_ids:
                selected_candidates.append(allowed[candidate_id])

        # 같은 구역의 작업을 하나로 묶은 후보가 선택됐다면 그 구역의 세부 후보를
        # 중복 태스크로 다시 만들지 않는다. 부록·서식을 삭제하는 규칙이 아니라,
        # 모델이 선택한 결과끼리만 합치는 문서 종류 비종속 후처리다.
        aggregate_sections = {
            candidate.section_type for candidate in selected_candidates
            if candidate.is_aggregate
        }
        selected_candidates = [candidate for candidate in selected_candidates
            if candidate.is_aggregate or candidate.section_type not in aggregate_sections]
        suggestions = []
        for candidate in selected_candidates:
            suggestions.append(TaskSuggestionExtraction(
                    title=candidate.title,
                    description=f"원문 근거: {candidate.text}",
                    due_on=candidate.due_on, actor=candidate.actor,
                    evidence_text=candidate.text, confidence=None,
                    quality_score=candidate.quality_score,
                    reason="원문에 실행 행동과 의무 표현이 함께 있어 후보로 선택됨"))
        return AnalyzeResult(result={"task_suggestions": [s.model_dump(mode="json") for s in suggestions],
            "candidate_count": len(candidates), "selected_count": len(suggestions),
            "call_count": runner.calls}, provider=self._ai_client.provider,
            prompt_version=ACTION_TASK_PROMPT_VERSION, **runner.metadata())

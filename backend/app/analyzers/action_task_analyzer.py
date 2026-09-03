import logging
import re

from app.analyzers.action_candidate_finder import find_action_candidates
from app.analyzers.output_schemas import ActionSelectionOutput
from app.analyzers.prompt_input import PromptBudget
from app.analyzers.prompts import ACTION_TASK_PROMPT_VERSION, build_action_task_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.schemas.extraction import TaskSuggestionExtraction

logger = logging.getLogger(__name__)
MAX_CANDIDATES_PER_GROUP = 12


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
            if group and (len(next_group) > MAX_CANDIDATES_PER_GROUP or not budget.fits(
                    build_action_task_prompt([c.as_prompt_record() for c in next_group]))):
                groups.append(group); group = [candidate]
            else:
                group = next_group
        if group:
            groups.append(group)
        selected_candidates = []
        failed_groups = []
        for index, candidates_group in enumerate(groups):
            # 모델에는 묶음마다 a1부터 시작하는 짧은 ID만 보여준다. 두 번째 묶음이
            # a19부터 시작하면 소형 모델이 학습된 a1을 되풀이하는 문제가 있었다.
            allowed = {f"a{offset}": candidate
                       for offset, candidate in enumerate(candidates_group, 1)}
            records = []
            for local_id, candidate in allowed.items():
                record = candidate.as_prompt_record()
                records.append({**record, "id": local_id})
            def verify(parsed, allowed=allowed):
                if not set(parsed.selected_ids) <= allowed.keys():
                    raise ValueError("unknown action candidate id")
                if len(set(parsed.selected_ids)) != len(parsed.selected_ids):
                    raise ValueError("duplicated action candidate id")
            stage = f"액션 태스크 선별 {index+1}/{len(groups)}"
            try:
                parsed = await runner.call(build_action_task_prompt(records),
                    ActionSelectionOutput, validate=verify, stage=stage)
            except BusinessError as exc:
                if exc.error_code is not ErrorCode.AI_INVALID_RESPONSE:
                    raise
                # 형식이 깨진 한 묶음 때문에 요약·분류 등 전체 분석을 폐기하지 않는다.
                failed_groups.append(index + 1)
                logger.warning("액션 태스크 묶음 제외 stage=%s", stage)
                continue
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
        # 일반 법령·예규의 잠재 의무와 아직 채택되지 않은 제안 약속은 실제 프로젝트
        # 태스크가 아니다. 모델이 골라도 구조 판정이 마지막 안전망이 된다.
        selected_candidates = [candidate for candidate in selected_candidates
            if candidate.actor_scope != "GENERIC_RULE"
            and candidate.statement_type != "PROPOSAL_COMMITMENT"]
        unique = []
        for candidate in selected_candidates:
            duplicate = next((existing for existing in unique
                if _same_action(existing, candidate)), None)
            if duplicate is None:
                unique.append(candidate)
            elif candidate.quality_score > duplicate.quality_score:
                unique[unique.index(duplicate)] = candidate
        selected_candidates = unique
        suggestions = []
        for candidate in selected_candidates:
            subject = candidate.actor or "담당자"
            due = f" {candidate.due_on.isoformat()}까지 완료해야 합니다." if candidate.due_on else ""
            action = _predicate(candidate.title)
            suggestions.append(TaskSuggestionExtraction(
                    title=candidate.title,
                    description=f"{subject}가 원문 요구사항에 따라 {action}합니다.{due}",
                    due_on=candidate.due_on, actor=candidate.actor,
                    actor_scope=candidate.actor_scope,
                    statement_type=candidate.statement_type,
                    task_kind=candidate.task_kind,
                    modality=candidate.modality,
                    recipient=_recipient(candidate.text),
                    relative_expression=candidate.relative_expression,
                    condition=candidate.condition,
                    evidence_text=candidate.text, confidence=None,
                    quality_score=candidate.quality_score,
                    reason="원문에 실행 행동과 의무 표현이 함께 있어 후보로 선택됨"))
        return AnalyzeResult(result={"task_suggestions": [s.model_dump(mode="json") for s in suggestions],
            "candidate_count": len(candidates), "selected_count": len(suggestions),
            "call_count": runner.calls, "failed_groups": failed_groups}, provider=self._ai_client.provider,
            prompt_version=ACTION_TASK_PROMPT_VERSION, **runner.metadata())


def _predicate(title: str) -> str:
    """명사형·연결형 제목 뒤에 붙여도 자연스러운 서술어로 정리한다."""
    value = title.rstrip(". ")
    value = re.sub(r"(?:하여|하시기|하기|하도록)$", "", value).rstrip()
    if re.search(r"(?:제출|작성|준비|신청|등록|확인|검토|보고|납품|송부|기재|발급|참석)$", value):
        return value + "해야 "
    return value + "을(를) 수행해야 "


def _recipient(text: str) -> str | None:
    found = re.search(r"(발주기관|사업주관\s*부서|계약담당자|담당자|수요기관)(?:에|에게|으로)", text)
    return re.sub(r"\s+", " ", found.group(1)) if found else None


def _same_action(left, right) -> bool:
    """표현이 달라도 행위·채널·핵심 대상이 같은 태스크를 하나로 본다."""
    def signature(candidate):
        text = f"{candidate.title} {candidate.text}"
        action = next((word for word in ("제출", "작성", "준비", "신청", "등록", "확인",
            "검토", "보고", "납품", "송부", "기재", "발급", "참석") if word in text), None)
        channel = next((word for word in ("나라장터", "이메일", "우편", "방문") if word in text), None)
        nouns = {word for word in ("제안서", "증빙서류", "서약서", "확인서", "계약서",
            "신청서류", "가격입찰서", "산출내역서") if word in text}
        return action, channel, nouns
    la, lc, ln = signature(left)
    ra, rc, rn = signature(right)
    if not la or la != ra or (lc and rc and lc != rc):
        return False
    if left.due_on != right.due_on and left.due_on and right.due_on:
        return False
    return bool(ln & rn) or (lc is not None and lc == rc)

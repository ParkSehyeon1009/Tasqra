import asyncio
from types import SimpleNamespace

from app.ai.fake_client import FakeAIClient
from app.ai.client_protocol import AIResult
from app.analyzers.action_candidate_finder import find_action_candidates
from app.analyzers.action_task_analyzer import ActionTaskAnalyzer
from app.analyzers.output_schemas import ActionSelectionOutput
from app.models.task_suggestion import TaskSuggestion
from app.services.task_suggestion_service import TaskSuggestionService


def config():
    return SimpleNamespace(AI_CONTEXT_TOKENS=8192, AI_MAX_OUTPUT_TOKENS=1536,
        AI_MAX_INPUT_CHARS=6000, AI_CHUNK_OVERLAP_CHARS=60, AI_MAX_CHUNKS=256,
        AI_CHUNK_RETRIES=1, AI_TIMEOUT_SECONDS=5)


def test_candidate_finder_marks_form_examples_and_groups_guide_without_hard_drop():
    text = """
접수기간 : 2026. 9. 10. ~ 2026. 9. 20. 접수방법 : 방문접수 접수장소 : 시청
※ 신청인은 모든 서류를 준비하여 제출해야 함
【 공적조서 및 구비서류 작성시 유의사항 】
경력증명서와 건강보험 확인서를 반드시 제출하여야 함
[별지 제1호서식]
홍길동은 신청서를 작성해야 함
"""
    candidates = find_action_candidates(text)
    titles = [candidate.title for candidate in candidates]
    assert "신청 서류 방문 제출" in titles
    assert "필수 신청서류 작성 및 증빙자료 준비" in titles
    example = next(candidate for candidate in candidates if "홍길동" in candidate.text)
    assert example.section_type in {"form_or_appendix", "example"}
    assert example.quality_score < 0.7


def test_action_analyzer_only_returns_grounded_candidates():
    analyzer = ActionTaskAnalyzer(FakeAIClient(), config())
    result = asyncio.run(analyzer.analyze("신청인은 증빙자료를 준비하여 제출해야 합니다."))
    assert result.result["candidate_count"] == 1
    assert result.result["selected_count"] == 1
    assert result.result["task_suggestions"][0]["evidence_text"] in "신청인은 증빙자료를 준비하여 제출해야 합니다."
    assert "원문 근거:" not in result.result["task_suggestions"][0]["description"]


def test_no_action_candidate_skips_model_call():
    result = asyncio.run(ActionTaskAnalyzer(FakeAIClient(), config()).analyze(
        "이 문서는 사업의 개요를 설명합니다."))
    assert result.result == {"task_suggestions": [], "candidate_count": 0,
        "selected_count": 0, "call_count": 0}


class SelectAllAI(FakeAIClient):
    async def generate_with_meta(self, prompt):
        import json
        records = json.loads(prompt.user)["candidates"]
        payload = ActionSelectionOutput(
            selected_ids=[record["id"] for record in records]).model_dump_json()
        return AIResult(text=payload, model_name=self.model_name,
            tokens_in=1, tokens_out=1, latency_ms=1)


def test_selected_aggregate_suppresses_only_same_section_details():
    text = """
접수기간 : 2026. 9. 10.까지 접수방법 : 방문접수 접수장소 : 시청
【 공적조서 및 구비서류 작성시 유의사항 】
경력증명서를 반드시 제출하여야 함
건강보험 확인서를 반드시 첨부하여야 함
"""
    result = asyncio.run(ActionTaskAnalyzer(SelectAllAI(), config()).analyze(text))
    suggestions = result.result["task_suggestions"]
    assert [item["title"] for item in suggestions] == [
        "신청 서류 방문 제출", "필수 신청서류 작성 및 증빙자료 준비"]


def test_reanalysis_approval_reuses_task_with_same_evidence():
    class DB:
        def commit(self): pass
        def rollback(self): pass
    item = TaskSuggestion(id=12, project_id=5, document_id=46, analysis_id=2,
        title="서류 제출", description="서류를 제출합니다.", due_on=None,
        actor=None, evidence_text="서류를 제출해야 함", evidence_fingerprint="same",
        confidence=None, quality_score=0.8, reason="근거 있음", decision="PENDING",
        decided_by=None, decided_at=None, source_text_revision=1,
        created_task_id=None)
    class Suggestions:
        def get(self, *_): return item
        def existing_task_id(self, *_): return 99
    class Tasks:
        def create_in_transaction(self, *_args, **_kwargs):
            raise AssertionError("같은 근거의 태스크를 다시 만들면 안 된다")
    row = TaskSuggestionService(DB(), Suggestions(), Tasks()).approve(5, 12, 1)
    assert row.created_task_id == 99
    assert row.decision == "APPROVED"
def test_정중한_송부_요청도_액션_후보로_잡는다():
    candidates = find_action_candidates(
        "협력업체에서는 계약서에 특이사항을 기입하시고 2부를 작성하여 우편으로 송부하여 주시면 됩니다.")

    assert candidates
    assert any("송부" in item.text for item in candidates)
    assert candidates[0].actor == "협력업체"


def test_줄_중간에서_끊긴_정중한_요청도_이어_읽는다():
    candidates = find_action_candidates(
        "계약서 2부를 작성하여 우편으로 송부하여\n주시면 진행하겠습니다.")
    assert any("송부" in item.text for item in candidates)


def test_숙지_문구는_태스크가_아니고_제출물은_짧은_제목을_쓴다():
    candidates = find_action_candidates("""
입찰자는 입찰설명서를 숙지하고 준수하여야 합니다.
제안서와 증빙서류는 반드시 나라장터를 통하여 제출하여 주시기 바랍니다.
""")
    assert [item.title for item in candidates] == ["제안서 및 증빙서류 나라장터 제출"]


class GroupAwareAI(FakeAIClient):
    def __init__(self, fail_second=False):
        self.calls = 0
        self.fail_second = fail_second
        self.group_ids = []

    async def generate_with_meta(self, prompt):
        import json
        self.calls += 1
        records = json.loads(prompt.user)["candidates"]
        ids = [record["id"] for record in records]
        self.group_ids.append(ids)
        selected = ["missing"] if self.fail_second and self.calls >= 2 else ids[:1]
        return AIResult(text=ActionSelectionOutput(selected_ids=selected).model_dump_json(),
            model_name=self.model_name, tokens_in=1, tokens_out=1, latency_ms=1)


def _many_actions(count=14):
    return "\n".join(
        f"담당자는 제안서 {number}번 항목을 작성하여 제출해야 합니다."
        for number in range(1, count + 1))


def test_각_묶음의_id는_a1부터_다시_시작한다():
    client = GroupAwareAI()
    result = asyncio.run(ActionTaskAnalyzer(client, config()).analyze(_many_actions()))
    assert len(client.group_ids) == 2
    assert all(ids[0] == "a1" for ids in client.group_ids)
    assert result.result["failed_groups"] == []


def test_깨진_묶음은_제외하고_앞선_선택을_보존한다():
    client = GroupAwareAI(fail_second=True)
    result = asyncio.run(ActionTaskAnalyzer(client, config()).analyze(_many_actions()))
    assert result.result["selected_count"] == 1
    assert result.result["failed_groups"] == [2]

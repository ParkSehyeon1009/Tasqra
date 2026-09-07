"""액션 태스크를 **어떤 문서 유형에서 돌릴지**의 계약.

왜 유형으로 가르나 (2026-09-07 실측, 실제 문서 3건):

    재공고서(RFP)        제안 19건 중 쓸 만한 것 1건
    제안요청서(RFP)      제안 10건 중 쓸 만한 것 **0건**
    과업지시서(CONTRACT)  제안  9건 중 쓸 만한 것 **9건**

공공 입찰 문서에서 「~하여야 한다」가 붙는 문장은 거의 전부 입찰 절차라,
후보 찾기가 정확할수록 절차만 골라온다. 규칙을 손봐서 될 문제가 아니다.

여기서 잠그는 것:
  ① CONTRACT 계열에서는 돈다
  ② RFP·PROPOSAL·REPORT 등에서는 **모델을 부르지 않는다**
  ③ 분류를 모르면 **거르지 않는다** (모른다고 기능이 사라지면 원인을 알 수 없다)
  ④ 건너뛴 것도 결과로 남는다 (「왜 제안이 없나」에 답할 수 있어야 한다)
  ⑤ 🔑 category 가 action_task 보다 **앞에** 있어야 한다 — 순서 의존이 있다
  ⑥ 다른 분석기는 이 규칙에 영향받지 않는다
"""
import asyncio

import pytest

from app.analyzers.protocol import AnalyzeResult
from app.services.analysis_service import (
    ACTION_TASK_CATEGORIES,
    DEFAULT_ANALYZER_TYPES,
    AnalysisService,
)


class 부른것을_세는분석기:
    prompt_version = "test-v1"

    def __init__(self, payload):
        self.payload, self.calls = payload, 0

    async def analyze(self, text, *, progress=None):
        self.calls += 1
        return AnalyzeResult(result=dict(self.payload), provider="test",
                             model_name="test", prompt_version=self.prompt_version)


def 서비스(registry):
    return AnalysisService(None, None, None, registry, None, None)


def 레지스트리(category=None):
    """category 는 분류 분석기가 낼 값. None 이면 분류를 아예 안 돌린다."""
    reg = {"action_task": 부른것을_세는분석기(
        {"task_suggestions": [{"title": "제출"}], "candidate_count": 3,
         "selected_count": 1, "call_count": 1})}
    if category is not None:
        reg["category"] = 부른것을_세는분석기({"category": category, "reason": "-"})
    return reg


@pytest.mark.parametrize("category", sorted(ACTION_TASK_CATEGORIES))
def test_계약_계열이면_돈다(category):
    reg = 레지스트리(category)
    results = asyncio.run(서비스(reg).analyze_text("본문", ["category", "action_task"]))

    assert reg["action_task"].calls == 1
    결과 = dict(results)["action_task"].result
    assert 결과["task_suggestions"], "제안이 사라졌다"
    assert "skipped" not in 결과


@pytest.mark.parametrize("category", ["RFP", "PROPOSAL", "REPORT", "MEETING_NOTES", "ETC"])
def test_그_밖의_유형이면_모델을_부르지_않는다(category):
    """⚠️ 결과만 비우는 게 아니라 **호출 자체를 안 한다.** 비용도 아껴야 한다."""
    reg = 레지스트리(category)
    results = asyncio.run(서비스(reg).analyze_text("본문", ["category", "action_task"]))

    assert reg["action_task"].calls == 0, "건너뛰기로 했는데 모델을 불렀다"
    결과 = dict(results)["action_task"].result
    assert 결과["task_suggestions"] == []
    assert category in 결과["skipped"], "왜 건너뛰었는지 남아 있어야 한다"


def test_분류를_모르면_거르지_않는다():
    """분류가 없다는 이유로 기능이 조용히 사라지면 사용자는 원인을 알 수 없다."""
    reg = 레지스트리(category=None)
    asyncio.run(서비스(reg).analyze_text("본문", ["action_task"]))
    assert reg["action_task"].calls == 1


def test_건너뛴_것도_결과로_남는다():
    reg = 레지스트리("RFP")
    results = asyncio.run(서비스(reg).analyze_text("본문", ["category", "action_task"]))

    이름들 = [name for name, _ in results]
    assert 이름들 == ["category", "action_task"], "건너뛴 분석기가 결과에서 빠졌다"
    건너뜀 = dict(results)["action_task"]
    # 모델을 안 불렀으므로 부른 척하지 않는다.
    assert 건너뜀.provider == "skipped"
    assert 건너뜀.result["call_count"] == 0


def test_기본_목록에서_category_가_action_task_보다_앞이다():
    """🔑 **순서 의존이 있다.** 뒤집히면 분류 결과를 못 보고 그냥 돌아버린다.

    _skip_reason 은 「앞서 나온 결과」에서 category 를 찾는다. 목록 순서가
    바뀌면 조용히 안 걸러지고, 그때는 노이즈가 다시 쌓이는 것으로만 드러난다.
    """
    assert "category" in DEFAULT_ANALYZER_TYPES
    assert "action_task" in DEFAULT_ANALYZER_TYPES
    assert (DEFAULT_ANALYZER_TYPES.index("category")
            < DEFAULT_ANALYZER_TYPES.index("action_task"))


def test_다른_분석기는_영향받지_않는다():
    reg = {"category": 부른것을_세는분석기({"category": "RFP", "reason": "-"}),
           "summary": 부른것을_세는분석기({"summary": "요약"}),
           "decision": 부른것을_세는분석기({"decisions": []})}
    asyncio.run(서비스(reg).analyze_text("본문", ["category", "summary", "decision"]))

    assert reg["summary"].calls == 1
    assert reg["decision"].calls == 1


def test_과업은_기본_분석에_들어가지_않는다():
    """🔴 2026-09-07: features 를 태스크 제안에 넣었다가 **뺐다.**

    「고정수리 운영」같은 사업 범위는 담당자에게 배정할 「할 일」이 아니라
    사업이 무엇인지에 대한 서술이라, 액션 태스크의 성격과 맞지 않는다.

    ⚠️ 태스크 제안으로 안 가면 남는 소비처가 없어 analyses 에 JSON 으로만
      쌓인다. 아무도 안 보는 결과에 문서당 8회 호출을 치를 이유가 없어
      기본 분석에서도 뺐다. 레지스트리에는 남아 있어 명시 호출은 된다.
    """
    assert "features" not in DEFAULT_ANALYZER_TYPES


def test_국소_오류_경로에서도_같은_규칙이_적용된다():
    """워커는 analyze_text_isolated 를 쓴다. 한쪽만 고치면 서비스에서 안 먹는다."""
    reg = 레지스트리("RFP")
    results, errors = asyncio.run(
        서비스(reg).analyze_text_isolated("본문", ["category", "action_task"]))

    assert reg["action_task"].calls == 0
    assert "skipped" in dict(results)["action_task"].result
    assert errors == [], "건너뛴 것은 오류가 아니다"

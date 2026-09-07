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
    FEATURES_CATEGORIES,
    AnalysisService,
    _features_as_suggestions,
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
    for name in ("action_task", "features"):
        assert name in DEFAULT_ANALYZER_TYPES
        assert (DEFAULT_ANALYZER_TYPES.index("category")
                < DEFAULT_ANALYZER_TYPES.index(name)), f"{name} 이 category 보다 앞이다"


def test_다른_분석기는_영향받지_않는다():
    reg = {"category": 부른것을_세는분석기({"category": "RFP", "reason": "-"}),
           "summary": 부른것을_세는분석기({"summary": "요약"}),
           "decision": 부른것을_세는분석기({"decisions": []})}
    asyncio.run(서비스(reg).analyze_text("본문", ["category", "summary", "decision"]))

    assert reg["summary"].calls == 1
    assert reg["decision"].calls == 1


class 과업분석기(부른것을_세는분석기):
    field = "features"          # save_results 가 저장 경로를 고르는 열쇠


@pytest.mark.parametrize("category", sorted(FEATURES_CATEGORIES))
def test_과업은_할_일이_적힌_문서에서_돈다(category):
    reg = {"category": 부른것을_세는분석기({"category": category, "reason": "-"}),
           "features": 과업분석기({"features": [{"name": "운영", "summary": "설명"}]})}
    asyncio.run(서비스(reg).analyze_text("본문", ["category", "features"]))
    assert reg["features"].calls == 1


@pytest.mark.parametrize("category", ["REPORT", "MEETING_NOTES", "ETC"])
def test_보고서_회의록에서는_과업을_뽑지_않는다(category):
    """⚠️ 정확도만이 아니라 **비용** 때문이다 — 구간마다 호출한다."""
    reg = {"category": 부른것을_세는분석기({"category": category, "reason": "-"}),
           "features": 과업분석기({"features": [{"name": "운영", "summary": "설명"}]})}
    results = asyncio.run(서비스(reg).analyze_text("본문", ["category", "features"]))

    assert reg["features"].calls == 0
    결과 = dict(results)["features"].result
    # 🔑 건너뛴 결과에도 **자기 필드**가 있어야 한다. save_results 가 키로
    #   저장 경로를 고르므로, task_suggestions 를 넣으면 엉뚱한 곳으로 간다.
    assert "features" in 결과 and 결과["features"] == []
    assert "task_suggestions" not in 결과


def test_제안요청서에서는_과업만_돌고_액션태스크는_안_돈다():
    """실측에서 갈린 지점이다 — 제안요청서에서 action_task 는 0/10 이었다."""
    reg = {"category": 부른것을_세는분석기({"category": "RFP", "reason": "-"}),
           "action_task": 부른것을_세는분석기({"task_suggestions": []}),
           "features": 과업분석기({"features": [{"name": "교통편 제공", "summary": "설명"}]})}
    asyncio.run(서비스(reg).analyze_text("본문", ["category", "action_task", "features"]))

    assert reg["action_task"].calls == 0
    assert reg["features"].calls == 1


# --- 과업 -> 태스크 제안 변환 ------------------------------------------------

def test_과업이_제안_모양으로_바뀐다():
    rows = _features_as_suggestions([
        {"name": "고정수리센터 운영", "summary": "267㎡ 규모로 운영한다.",
         "source_text": "○ 고정수리센터를 운영한다."}])
    assert rows[0]["title"] == "고정수리센터 운영"
    assert rows[0]["description"] == "267㎡ 규모로 운영한다."
    # 사업 범위이지 기한 있는 의무가 아니다.
    assert rows[0]["statement_type"] == "SCOPE"
    assert "○ 고정수리센터를 운영한다." in rows[0]["evidence_text"]


def test_같은_구간에서_나온_항목은_근거가_서로_달라야_한다():
    """🔑 **승인이 깨지는 자리다.**

    evidence_text 의 해시가 evidence_fingerprint 가 되고,
    TaskSuggestionService.approve 는 그것으로 「이미 태스크를 만든 근거인가」를
    본다. 항목마다 지문이 같으면 첫 승인만 태스크를 만들고 나머지는 그 태스크에
    붙어버린다 — 사용자는 승인했는데 태스크가 안 생긴 것으로 보인다.
    """
    구간 = "○ 고정수리센터와 이동수리센터를 운영한다."
    rows = _features_as_suggestions([
        {"name": "고정수리센터 운영", "summary": "가", "source_text": 구간},
        {"name": "이동수리센터 운영", "summary": "나", "source_text": 구간}])

    근거들 = [r["evidence_text"] for r in rows]
    assert len(set(근거들)) == 2, "같은 구간의 항목들이 같은 근거를 갖는다"
    for 근거 in 근거들:
        assert 구간 in 근거, "근거 구간은 여전히 들어 있어야 한다"


# --- 분석기 간 중복 제거 --------------------------------------------------

def test_액션태스크가_이미_낸_일은_과업으로_또_만들지_않는다():
    """실측: 과업지시서에서 「작업 사진 제출」이 양쪽에 나왔다.

    features 제목은 짧은 명사구, action_task 제목은 원문 문장이라
    **짧은 쪽의 낱말이 긴 쪽에 전부 있으면** 같은 일로 본다.
    """
    이미 = ['“계약당사자”는 주요 수리 장소별로 각 작업 사진을 촬영하여 제출']
    rows = _features_as_suggestions(
        [{"name": "작업 사진 제출", "summary": "가", "source_text": "본문"},
         {"name": "고정수리 운영", "summary": "나", "source_text": "본문"}], 이미)

    assert [r["title"] for r in rows] == ["고정수리 운영"]


def test_낱말이_하나면_합치지_않는다():
    """⚠️ 「보고」 하나로 합치면 무관한 문장에도 걸린다."""
    이미 = ["시설물을 손괴하였을 경우 즉시 발주처에게 보고하고 복구"]
    rows = _features_as_suggestions(
        [{"name": "보고", "summary": "가", "source_text": "본문"}], 이미)
    assert len(rows) == 1, "낱말 하나짜리를 합쳐버렸다"


def test_일부만_겹치면_합치지_않는다():
    """🔑 **덜 합치는 쪽으로 기운다.**

    과하게 합치면 과업이 사라지고 아무도 못 알아채지만, 덜 합치면 비슷한
    카드가 둘 떠서 승인 화면에서 지우면 된다.
    """
    이미 = ["시설물을 손괴하였을 경우 즉시 발주처에게 보고하고 복구"]
    rows = _features_as_suggestions(
        [{"name": "시설물 안전 점검", "summary": "가", "source_text": "본문"}], 이미)
    assert len(rows) == 1, "「시설물」만 겹치는데 합쳐버렸다"


def test_흔한_낱말은_비교에서_뺀다():
    """「관리」·「운영」같은 말은 어느 문장에나 있어 겹침이 의미가 없다."""
    이미 = ["용역 수행과 관련하여 발주처의 지시에 따라 시설을 관리하고 운영"]
    rows = _features_as_suggestions(
        [{"name": "수리물품 관리", "summary": "가", "source_text": "본문"}], 이미)
    assert len(rows) == 1


def test_앞서_나온_제목을_결과에서_모은다():
    from app.services.analysis_service import _앞서_나온_제목들

    results = [("action_task", AnalyzeResult(
        result={"task_suggestions": [{"title": "착수신고서 제출"}, {"title": "월간 보고"}]},
        provider="t", model_name="t", prompt_version="t"))]
    assert _앞서_나온_제목들(results) == ["착수신고서 제출", "월간 보고"]


def test_근거_구간이_없어도_비어_있지_않다():
    """evidence_text 는 NOT NULL 이고 min_length=1 이다."""
    rows = _features_as_suggestions([{"name": "운영", "summary": "설명"}])
    assert rows[0]["evidence_text"].strip()


def test_국소_오류_경로에서도_같은_규칙이_적용된다():
    """워커는 analyze_text_isolated 를 쓴다. 한쪽만 고치면 서비스에서 안 먹는다."""
    reg = 레지스트리("RFP")
    results, errors = asyncio.run(
        서비스(reg).analyze_text_isolated("본문", ["category", "action_task"]))

    assert reg["action_task"].calls == 0
    assert "skipped" in dict(results)["action_task"].result
    assert errors == [], "건너뛴 것은 오류가 아니다"

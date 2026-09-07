"""FeaturesAnalyzer 의 계약 — 구간 분할·중복 합치기·전체 상한.

test_ai_analysis.py 와 같은 방식으로 모델 없이 검증한다. 여기서 잠그는 것은
**결정사항 분석기에서 그대로 가져오지 않고 새로 정한 것들**이다:

  ① 프롬프트에 start·end 를 넣지 않는다   (넣으면 학습·서비스 불일치)
  ② 이름이 같으면 합치고 설명이 긴 쪽을 남긴다
  ③ 이름이 다르면 합치지 않는다            (덜 합치는 쪽으로 기운다)
  ④ 전체 상한을 넘으면 잘라내되 **기록한다**
  ⑤ 빈 구간은 정상이며 통계로 남는다
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.ai.client_protocol import AIResult
from app.analyzers.features_analyzer import (
    _NAME_CAP,
    _SUMMARY_CAP,
    FeaturesAnalyzer,
    _merge_key,
)


@pytest.fixture
def config():
    # AI_MAX_INPUT_CHARS 를 작게 잡아 짧은 본문도 여러 구간으로 쪼개지게 한다.
    return SimpleNamespace(AI_CONTEXT_TOKENS=8192, AI_MAX_OUTPUT_TOKENS=1536,
        AI_MAX_INPUT_CHARS=600, AI_CHUNK_OVERLAP_CHARS=60, AI_MAX_CHUNKS=256,
        AI_CHUNK_RETRIES=1, AI_TIMEOUT_SECONDS=5, AI_MAX_FEATURES=40)


class ScriptedAI:
    provider = "test"
    model_name = "test"

    def __init__(self, answer):
        self.answer, self.requests = answer, []

    async def generate_with_meta(self, prompt):
        self.requests.append(prompt)
        value = self.answer(prompt, len(self.requests))
        return AIResult(text=json.dumps(value, ensure_ascii=False),
                        model_name="test", tokens_in=10, tokens_out=5)


def 과업(name, summary="무엇을 하는 일인지 적는다."):
    return {"name": name, "summary": summary}


def test_프롬프트에_구간번호를_넣지_않는다(config):
    """⚠️ 모델은 `{"document": ...}` 하나로 학습했다.

    build_decision_prompt 는 start·end 를 넣는데, 그것을 그대로 따라 하면
    모델이 본 적 없는 입력이 되어 파인튜닝 효과가 깎인다.
    """
    ai = ScriptedAI(lambda p, n: {"features": []})
    asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 2000))

    assert ai.requests, "호출이 없었다"
    for request in ai.requests:
        data = json.loads(request.user)
        assert set(data) == {"document"}, f"user 메시지에 {set(data)} 가 들어갔다"


def test_같은_이름은_합치고_긴_설명을_남긴다(config):
    """구간이 겹치므로 경계의 과업은 두 번 나온다."""
    def answer(prompt, n):
        if n == 1:
            return {"features": [과업("굿즈 제작", "굿즈를 만든다.")]}
        if n == 2:
            return {"features": [과업("굿즈  제작", "굿즈를 만들어 3차에 걸쳐 납품한다.")]}
        return {"features": []}

    ai = ScriptedAI(answer)
    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 2000))
    items = result.result["features"]

    assert len(items) == 1, f"공백만 다른 이름이 안 합쳐졌다: {items}"
    # 문맥을 더 많이 본 쪽(설명이 긴 쪽)이 남아야 한다.
    assert items[0]["summary"] == "굿즈를 만들어 3차에 걸쳐 납품한다."


def test_이름이_다르면_합치지_않는다(config):
    """⚠️ **덜 합치는 쪽으로 기운다.**

    「굿즈 제작」과 「굿즈 제작 및 분할 납품」은 사람 눈에는 같은 일이지만
    합치지 않는다. 과하게 합치면 과업이 사라지고 아무도 못 알아채는 반면,
    덜 합치면 비슷한 항목이 둘 떠서 승인 화면에서 지울 수 있기 때문이다.
    """
    def answer(prompt, n):
        if n == 1:
            return {"features": [과업("굿즈 제작")]}
        if n == 2:
            return {"features": [과업("굿즈 제작 및 분할 납품")]}
        return {"features": []}

    ai = ScriptedAI(answer)
    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 2000))
    assert len(result.result["features"]) == 2


def test_전체_상한을_넘으면_잘라내고_기록한다(config):
    """구간당 12개 상한만으로는 부족하다 — 구간이 20개면 240개가 된다."""
    config.AI_MAX_FEATURES = 3
    ai = ScriptedAI(lambda p, n: {"features": [과업(f"과업 {n}-{i}") for i in range(4)]})

    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 3000))

    assert len(result.result["features"]) == 3
    # 조용히 버리면 「원래 그만큼이었다」와 구별할 수 없다.
    assert result.result["capped_at"] == 3


def test_상한에_안_걸리면_capped_at_은_None(config):
    ai = ScriptedAI(lambda p, n: {"features": [과업("과업 하나")]})
    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 2000))
    assert result.result["capped_at"] is None


def test_빈_구간은_정상이며_통계로_남는다(config):
    """⚠️ 결정사항과 같은 필드지만 읽는 법이 다르다.

    공고문은 대부분의 구간에 과업이 없다. 빈 구간은 경고가 아니다.
    """
    def answer(prompt, n):
        return {"features": [과업("유일한 과업")]} if n == 1 else {"features": []}

    ai = ScriptedAI(answer)
    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 3000))

    assert result.result["features"], "과업이 있는 구간까지 버려졌다"
    assert result.result["empty_chunks"], "빈 구간이 기록되지 않았다"
    assert 1 not in result.result["empty_chunks"]


def test_상한에_딱_맞는_값을_센다(config):
    """제약 디코딩이 상한에서 문자열을 끊는다 — 유효한 JSON 이라 검증은 통과한다.

    ⚠️ 길이를 숫자로 적지 않고 스키마에서 가져온다. 상한을 올렸을 때 이 테스트가
      조용히 무의미해지지 않게 하려는 것이다(30/150 -> 40/200 으로 올린 적이 있다).
    """
    ai = ScriptedAI(lambda p, n: {"features": [과업("가" * _NAME_CAP, "나" * _SUMMARY_CAP)]}
                    if n == 1 else {"features": []})
    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 2000))
    assert result.result["at_length_cap"] == 1


def test_상한보다_짧으면_세지_않는다(config):
    ai = ScriptedAI(lambda p, n: {"features": [과업("가" * (_NAME_CAP - 1),
                                                  "나" * (_SUMMARY_CAP - 1))]}
                    if n == 1 else {"features": []})
    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 2000))
    assert result.result["at_length_cap"] == 0


def test_긴_문서를_구간으로_덮는다(config):
    """실제 문서의 64%가 6,000자를 넘는다. 앞부분만 보면 뒤의 과업을 놓친다."""
    ai = ScriptedAI(lambda p, n: {"features": []})
    result = asyncio.run(FeaturesAnalyzer(ai, config).analyze("가" * 5000))

    assert result.result["chunk_count"] > 1
    합친길이 = sum(len(json.loads(r.user)["document"]) for r in ai.requests)
    assert 합친길이 >= 5000, "원문을 다 덮지 못했다"


def test_merge_key_는_공백과_문장부호를_지운다():
    assert _merge_key("굿즈 제작") == _merge_key("굿즈  제작")
    assert _merge_key("현황 및 수요분석") == _merge_key("현황·및·수요분석")
    assert _merge_key("굿즈 제작") != _merge_key("굿즈 제작 및 납품")

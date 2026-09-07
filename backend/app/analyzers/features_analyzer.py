"""문서 전체를 구간으로 나눠 **수행할 과업**을 뽑고 중복을 합친다.

왜 요약이 아니라 결정사항을 본떴는가: 출력이 문자열 하나가 아니라 **목록**이다.
요약은 구간별 인용을 뽑아 SELECT·FINAL 로 다시 써야 하지만, 과업은 이미 목록이라
구간별로 뽑아 합치면 된다. extraction_analyzer.DecisionAnalyzer 와 같은 모양이다.

왜 구간을 나누는가 — **실제 문서의 64%가 한 번에 안 들어간다.**
`AI_MAX_INPUT_CHARS` 가 6,000 인데 실측 코퍼스 103건 중 66건이 그보다 길다.
앞부분만 보고 판단하면 과업이 뒤에 있는 문서를 통째로 놓친다. 실제로 2026-09-04
측정에서 11,873자 공고문의 앞 6,000자가 전부 입찰 절차였고, 모델은 볼 수 있는
과업이 없는 상태에서 보일러플레이트를 과업으로 내놓았다.

왜 인용을 요구하지 않는가: 과업은 사람이 승인하기 전까지 제안으로만 남는다
(결정사항과 같다). 승인 화면이 곧 검증이므로 원문 대조를 파이프라인에서
강제하지 않는다.

⚠️ **구간을 나누면 지어냄이 줄지 않는다. 늘어난다.** 절차성 구간마다 12개를 채울
   기회가 생기기 때문이다. 그래서 전체 상한(AI_MAX_FEATURES)을 따로 걸고, 잘렸을
   때 결과에 남긴다. 조용히 버리면 「원래 그만큼이었다」와 구별할 수 없다.
"""
from app.analyzers.output_schemas import Feature, FeaturesOutput
from app.analyzers.prompt_input import PromptBudget, split_document
from app.analyzers.prompts import FEATURES_PROMPT_VERSION, build_features_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings

# 상한에 **딱 맞는** 값은 디코더가 거기서 끊은 것일 수 있다. output_schemas 의
# Feature 주석 참고 — 유효한 JSON 이라 검증으로는 안 걸린다. 세어서 남긴다.
#
# ⚠️ 스키마에서 가져온다. 여기에 숫자를 적어두면 스키마만 올렸을 때 조용히
#   갈라져서, 안 잘린 항목을 잘렸다고 세게 된다.


def _cap(field: str) -> int:
    """Feature 의 max_length. metadata 에는 제약이 여러 개 섞여 있다.

    ⚠️ metadata[-1] 로 집으면 안 된다 — NonEmpty 의 StringConstraints 가 잡혀
      max_length 가 None 으로 나온다(실제로 그렇게 틀렸다). 값이 있는 것을 찾는다.
    """
    for 제약 in Feature.model_fields[field].metadata:
        길이 = getattr(제약, "max_length", None)
        if 길이 is not None:
            return 길이
    raise RuntimeError(f"Feature.{field} 에 max_length 가 없다")


_NAME_CAP = _cap("name")
_SUMMARY_CAP = _cap("summary")


def _sizing_prompt(text: str, start: int, end: int):
    """split_document 가 구간 크기를 재려고 부르는 어댑터.

    ⚠️ start·end 를 **버린다.** split_document 는 builder(text, start, end) 로
      부르지만(prompt_input.py:51), 과업 프롬프트는 `{"document": ...}` 하나만
      받는다. 모델이 그 모양으로 학습했기 때문이고, 구간 번호를 덧붙이면 본 적
      없는 입력이 된다. build_features_prompt 의 주석 참고.
    """
    return build_features_prompt(text)


def _merge_key(name: str) -> str:
    """중복 판정용 이름. 공백·문장부호를 지운 것.

    ⚠️ **덜 합치는 쪽으로 기울였다.** 구간이 겹치므로 경계의 과업은 두 번 나오고,
      같은 일을 구간마다 다르게 부른다(「굿즈 제작」 대 「굿즈 제작 및 분할 납품」).
      낱말 겹침 같은 퍼지 매칭으로 합치면 그런 것도 잡히지만 **서로 다른 과업을
      합칠 위험**이 함께 온다.

      두 실패의 무게가 다르다:
        과하게 합침 -> 과업이 사라진다. 사람이 알아챌 방법이 없다
        덜 합침     -> 비슷한 항목이 둘 뜬다. 보이고, 승인 화면에서 지우면 된다

      복구 가능한 쪽을 고른다. 정확히 같은 이름만 합친다.
    """
    return "".join(ch for ch in name if ch.isalnum())


class FeaturesAnalyzer:
    prompt_version = FEATURES_PROMPT_VERSION
    stage_label = "과업 추출"
    field = "features"

    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        budget = PromptBudget(self._settings)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        chunks = split_document(text, budget, _sizing_prompt,
            overlap=self._settings.AI_CHUNK_OVERLAP_CHARS, max_chunks=self._settings.AI_MAX_CHUNKS)
        cap = getattr(self._settings, "AI_MAX_FEATURES", 40)

        found, seen, empty_chunks = [], {}, []
        capped = False
        clipped = 0
        for i, chunk in enumerate(chunks):
            stage = f"{self.stage_label} {i + 1}/{len(chunks)}"
            runner.progress(stage, i, len(chunks))
            parsed = await runner.call(build_features_prompt(chunk.text),
                FeaturesOutput, stage=stage)
            if not parsed.features:
                # ⚠️ 경고가 아니다. 과업에서는 **빈 구간이 정상**이다 — 공고문은
                #   대부분의 구간에 과업이 없다. 결정사항 쪽과 같은 필드지만
                #   읽는 법이 다르다. 통계로만 쓴다.
                empty_chunks.append(i + 1)
            for item in parsed.features:
                if len(item.name) >= _NAME_CAP or len(item.summary) >= _SUMMARY_CAP:
                    clipped += 1
                key = _merge_key(item.name)
                at = seen.get(key)
                if at is None:
                    if len(found) >= cap:
                        capped = True
                        continue
                    seen[key] = len(found)
                    found.append((item, chunk))
                elif len(item.summary) > len(found[at][0].summary):
                    # 경계에 걸친 항목은 문맥을 더 많이 본 쪽의 설명이 길다.
                    # 결정사항이 confidence 로 고르는 자리인데, 과업 스키마에는
                    # confidence 가 없다 — 3B 모델의 자기 확신도를 믿기 어려워
                    # 넣지 않았다(schedule_analyzer 가 같은 이유로 날짜를 뺐다).
                    found[at] = (item, chunk)
            runner.progress(stage, i + 1, len(chunks))

        return AnalyzeResult(
            result={self.field: [{**item.model_dump(mode="json"),
                                  # ⚠️ **어느 구간에서 나왔는지 남긴다.**
                                  #   이 분석기는 생성 방식이라 「원문 그대로의
                                  #   인용」이 없다. 그래도 승인하는 사람은 무엇을
                                  #   보고 만든 것인지 대조할 수 있어야 한다.
                                  #   태스크 제안으로 옮길 때 evidence_text 가
                                  #   되며, 그 자리는 비워둘 수 없다.
                                  "source_start": chunk.start,
                                  "source_end": chunk.end,
                                  "source_text": chunk.text}
                                 for item, chunk in found],
                    "chunk_count": len(chunks), "empty_chunks": empty_chunks,
                    # 잘렸다는 것을 남긴다. 이게 없으면 「원래 그만큼」과 구별이 안 된다.
                    "capped_at": cap if capped else None,
                    # 상한에 딱 맞는 값의 개수. 크면 디코더가 자르고 있다는 뜻이다.
                    "at_length_cap": clipped,
                    "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=self.prompt_version,
            **runner.metadata())

"""문서 전체를 구간으로 나눠 결정사항을 뽑고 중복을 합친다.

왜 구간을 나누는가: category_analyzer 는 앞·중간·뒤 표본만 본다(sample_input).
분류는 그것으로 충분하지만 **추출은 아니다** — 표본에 안 들어간 구간의 결정은
그냥 없어지고, 빠뜨린 것을 사람이 알아챌 방법도 없다. 그래서 summary_analyzer
처럼 전체를 덮는다.

왜 요약처럼 근거 인용을 요구하지 않는가: 결정사항은 사람이 승인하기 전까지
PENDING 제안으로만 남는다(DecisionScheduleWriter). 승인 화면이 곧 검증이므로
원문 대조를 파이프라인에서 강제하지 않는다. 대신 confidence 를 받아 정렬한다.

⚠️ 일정은 이 방식을 쓰지 않는다. schedule_analyzer.py 를 보라 — 3B 모델이
   날짜 필드를 못 채워서 날짜 찾기를 파이썬으로 옮겼다.
"""
from app.analyzers.output_schemas import DecisionsOutput
from app.analyzers.prompt_input import PromptBudget, split_document
from app.analyzers.prompts import DECISION_PROMPT_VERSION, build_decision_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings


class DecisionAnalyzer:
    prompt_version = DECISION_PROMPT_VERSION
    stage_label = "결정사항 추출"
    field = "decisions"

    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        budget = PromptBudget(self._settings)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        chunks = split_document(text, budget, build_decision_prompt,
            overlap=self._settings.AI_CHUNK_OVERLAP_CHARS, max_chunks=self._settings.AI_MAX_CHUNKS)

        found, seen, empty_chunks = [], {}, []
        for i, chunk in enumerate(chunks):
            stage = f"{self.stage_label} {i + 1}/{len(chunks)}"
            runner.progress(stage, i, len(chunks))
            parsed = await runner.call(
                build_decision_prompt(chunk.text, chunk.start, chunk.end),
                DecisionsOutput, stage=stage)
            if not parsed.decisions:
                empty_chunks.append(i + 1)
            for item in parsed.decisions:
                # 구간이 앞뒤로 겹치므로 경계의 결정은 두 번 나온다. 같은 결정을
                # 두 구간이 다르게 요약할 수 있어 제목만으로는 못 합친다 —
                # 날짜와 상태까지 같아야 같은 것으로 본다.
                key = (item.title.strip(), item.status, item.decided_on)
                at = seen.get(key)
                if at is None:
                    seen[key] = len(found)
                    found.append(item)
                elif (item.confidence or 0) > (found[at].confidence or 0):
                    # 경계에 걸친 항목은 문맥을 더 많이 본 쪽이 대개 확신이 높다.
                    found[at] = item
            runner.progress(stage, i + 1, len(chunks))

        return AnalyzeResult(
            result={self.field: [item.model_dump(mode="json") for item in found],
                    "chunk_count": len(chunks), "empty_chunks": empty_chunks,
                    "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=self.prompt_version,
            **runner.metadata())

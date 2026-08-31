# =============================================================================
# 이 파일의 책임: LLM으로 텍스트를 분석(요약/카테고리 분류 등)하는 모든
#   분석기가 만족해야 할 "계약(Protocol)"을 정의한다. 새 분석기를 추가해도
#   기존 코드(라우터/서비스)는 수정되지 않아야 한다 (§2-3 Protocol 기반 확장).
# 다른 파일과의 관계: summary_analyzer.py / category_analyzer.py(담당자 B가 구현)가
#   이 Protocol을 구현하고, 내부에서 AIClientProtocol.generate_with_meta()를
#   호출해 AnalyzeResult를 만든다. analysis_service.py는 AnalyzeResult를 그대로
#   Analysis 엔티티(provider/model_name/tokens_in/tokens_out/latency_ms)에 옮겨 담는다.
#   result 필드는 분석기마다 구조가 달라 dict[str, Any]로 열어두어, 분석기가
#   추가돼도 API 응답(§7 analyses[].result) 스펙이 바뀌지 않게 한다.
# Spring 비교: Java interface(Analyzer)와 동일. AIClientProtocol이 async이므로
#   analyze()도 async로 선언한다 (§5: POST /documents/{id}/analyze만 async 라우터).
# =============================================================================

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AnalyzeResult:
    result: dict[str, Any]
    provider: str
    model_name: str
    prompt_version: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None


class Analyzer(Protocol):
    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        ...

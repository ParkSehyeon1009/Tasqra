# =============================================================================
# 이 파일의 책임: AI 클라이언트가 반드시 구현해야 할 "계약(인터페이스)"만 정의한다.
#   실제 구현(OpenAI 연동, Fake 등)은 이 Protocol에 의존하지 않고 이 Protocol을
#   "만족"시키기만 하면 된다 (구조적 타이핑, structural typing).
# 다른 파일과의 관계: fake_client.py와 openai_client.py가 이 Protocol을 구현한다.
#   서비스 레이어(추후 생성될 services/)는 이 AIClientProtocol 타입에만 의존하고,
#   Depends()로 실제 구현체(Fake 또는 OpenAI)를 주입받는다.
# Spring 비교: Java의 interface(AIClient)와 동일한 역할.
#   차이점은 Python의 Protocol은 명시적으로 "implements"를 선언할 필요가 없다는 것
#   (덕 타이핑 기반). 즉 클래스가 implements를 안 써도 메서드 시그니처만 맞으면
#   타입 체커(mypy/pyright)가 해당 클래스를 이 Protocol을 만족하는 것으로 인정한다.
# =============================================================================

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class AIRequest:
    system: str
    user: str
    prompt_version: str
    max_output_tokens: int = 1536
    # 이 호출이 어떤 모양의 JSON 을 기대하는지. analyzers/runner.py 가
    # 검증에 쓸 스키마를 그대로 실어 보낸다. 값이 있으면 클라이언트가 서버에
    # 넘겨 **디코딩 단계에서 문법으로 강제**할 수 있다(response_format 참고).
    response_schema: type[BaseModel] | None = None

    def messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system},
                {"role": "user", "content": self.user}]

    def response_format(self) -> dict:
        """서버에 보낼 response_format 을 만든다.

        json_object 는 "JSON 이기만 하면" 통과시킨다. 그래서 파인튜닝 모델이
        Literal 필드에 한자를 섞어 뱉으면(`확定`) 서버는 그대로 돌려주고,
        Pydantic 검증에서야 걸려 재시도만 반복한다.

        json_schema 는 서버가 스키마대로 **디코딩을 제약**하므로 애초에 그 값이
        나올 수 없다. 실측으로 확인했다 — 같은 프롬프트·같은 모델에서
        json_object 는 ValidationError, json_schema 는 status 6개 전부 정상.
        """
        if self.response_schema is None:
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": self.response_schema.__name__,
                "schema": self.response_schema.model_json_schema(),
                "strict": True,
            },
        }


# AIResult: generate_with_meta()의 반환 타입. 본프로젝트에서 자체 파인튜닝 모델과
# 상용 API의 비용/성능을 비교해야 하므로, 응답 텍스트뿐 아니라 토큰 사용량·지연 시간·
# 모델명까지 함께 들고 다닌다 (analyses 테이블에 그대로 저장됨).
@dataclass(frozen=True)
class AIResult:
    text: str
    model_name: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None


class AIClientProtocol(Protocol):
    # 이 클라이언트가 어떤 제공자인지 나타내는 라벨("fake"/"openai"/"local").
    # analyses.provider 컬럼에 그대로 저장되어, 로컬 모델과 상용 API의
    # 비용/성능을 비교할 때의 기준이 된다. 분석기가 isinstance로 구현체를
    # 판별하지 않아도 되도록 클라이언트 자신이 들고 있는다.
    provider: str

    # 편의 메서드. 구현체는 generate_with_meta()를 호출해
    # .text만 반환하는 방식으로 만들어 로직 중복을 피한다.
    async def generate(self, prompt: AIRequest) -> str:
        ...

    # 신규: 토큰 사용량/지연 시간 등 메타 정보를 포함해 반환한다.
    async def generate_with_meta(self, prompt: AIRequest) -> AIResult:
        ...

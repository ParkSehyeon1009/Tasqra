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
    # 기존 유지 (하위 호환). 구현체는 보통 generate_with_meta()를 호출해
    # .text만 반환하는 방식으로 만들어 로직 중복을 피한다.
    async def generate(self, prompt: str) -> str:
        ...

    # 신규: 토큰 사용량/지연 시간 등 메타 정보를 포함해 반환한다.
    async def generate_with_meta(self, prompt: str) -> AIResult:
        ...

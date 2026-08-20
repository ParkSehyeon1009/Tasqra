# =============================================================================
# 이 파일의 책임: 텍스트를 벡터로 바꾸는 모든 임베딩 클라이언트가 만족해야 할
#   "계약(Protocol)"을 정의한다. 실제 구현(가짜 · 로컬 서버 · 라이브러리 직접
#   호출)은 이 Protocol 에 의존하지 않고 시그니처만 맞추면 된다.
# 다른 파일과의 관계: fake_client.py 와 local_client.py 가 이 Protocol 을 구현한다.
#   services/chunking_service.py 는 이 타입에만 의존하므로 어느 구현이 꽂혀
#   있는지 모른다. dependencies.py 의 get_embedding_client() 가 settings 를 보고
#   구현체를 고른다 (get_ai_client() 와 같은 방식).
#   models/chunk.py 의 EMBEDDING_DIM(1024) 과 dimension 이 반드시 일치해야 한다.
#   document_chunks 에 embedding_dim = 1024 CHECK 제약이 걸려 있어, 다르면
#   INSERT 가 실패한다.
# Spring 비교: Java interface(EmbeddingClient)와 동일하다. ai/client_protocol.py
#   의 AIClientProtocol 과 짝을 이루지만, 이쪽은 async 가 아니라 동기다.
#   이유는 extractors/protocol.py 의 TextExtractor.extract 와 같다 — 임베딩은
#   Celery 워커 안에서 배치로 돌고, 그 워커가 동기 코드이기 때문이다.
#   LLM 호출(generate)만 async 인 것과 대조된다.
# =============================================================================

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmbeddingResult:
    """임베딩 한 묶음의 결과와 그것을 만든 조건.

    벡터만 돌려주면 나중에 "이 벡터를 무슨 모델로 만들었나"를 알 수 없다.
    document_chunks.embedding_model / embedding_dim 에 그대로 기록해야 하므로
    (기능명세서 RAG-001-2 판정 기준) 벡터와 함께 반환한다.
    """

    vectors: tuple[tuple[float, ...], ...]
    # document_chunks.embedding_model 에 들어가는 값. String(100) 이라 넘치면
    # 잘리므로 구현체가 알아서 100자 안으로 준다.
    model: str
    dimension: int


class EmbeddingClientProtocol(Protocol):
    """텍스트 목록을 같은 순서의 벡터 목록으로 바꾼다.

    배치를 받는 이유는 두 가지다.
      (1) 로컬 모델이든 HTTP 든 한 번에 여러 개를 넣는 것이 훨씬 빠르다.
      (2) 청크는 문서 하나에 수백 개가 나오므로 한 개씩 호출하면 왕복이 낭비다.
    """

    @property
    def model_name(self) -> str:
        """document_chunks.embedding_model 에 기록할 이름."""
        ...

    @property
    def dimension(self) -> int:
        """출력 벡터의 차원. models/chunk.py 의 EMBEDDING_DIM 과 같아야 한다."""
        ...

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        """문서(청크) 쪽 텍스트를 임베딩한다."""
        ...

    def embed_query(self, text: str) -> EmbeddingResult:
        """검색 질의를 임베딩한다.

        문서 쪽과 나눠 둔 이유: 모델에 따라 질의에만 접두어를 붙여야 하는 것이
        있다(예: E5 계열의 "query: "). BGE-M3 계열은 양쪽 다 접두어가 없지만,
        모델을 바꿀 때 서비스 코드를 고치지 않으려면 구분이 여기 있어야 한다.
        """
        ...

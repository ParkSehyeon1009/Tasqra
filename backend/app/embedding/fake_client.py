# =============================================================================
# 이 파일의 책임: protocol.py 의 EmbeddingClientProtocol 을 구현하되, 실제 모델을
#   전혀 쓰지 않고 텍스트 해시로 벡터를 만든다. 임베딩 라이브러리(torch 약 1GB) ·
#   모델 가중치(약 2.3GB) · 네트워크 없이 청킹 -> 저장 -> 검색 파이프라인 전체를
#   끝까지 돌려볼 수 있게 하는 것이 목적이다.
#
#   두 가지를 보장한다.
#     (1) 결정적(deterministic) — 같은 텍스트는 항상 같은 벡터가 된다. 그래야
#         재실행해도 결과가 같고 테스트가 흔들리지 않는다.
#     (2) 정규화됨 — 길이가 1 인 벡터를 준다. document_chunks 의 HNSW 인덱스가
#         vector_cosine_ops 라서, 정규화돼 있으면 코사인 거리 계산이 실제 모델과
#         같은 성질을 갖는다. 실행계획(EXPLAIN ANALYZE) 검증에 그대로 쓸 수 있다.
#
#   !! 의미는 없다. 같은 뜻의 다른 문장이 가까워지지 않는다. 검색 "동작"을
#      검증할 수는 있지만 검색 "품질"은 이걸로 잴 수 없다.
#
# 다른 파일과의 관계: ai/fake_client.py 의 FakeAIClient 와 같은 자리다.
#   dependencies.py 가 settings.USE_FAKE_EMBEDDING 이 True 일 때 이것을 준다.
#   기본값이 True 인 이유도 FakeAIClient 와 같다 — 무거운 것이 실수로
#   켜지지 않게 하는 안전장치다.
# Spring 비교: 테스트용 스텁 구현체를 @Profile("fake") 로 등록해 두는 것과 같다.
# =============================================================================

from __future__ import annotations

import hashlib
import math

from app.embedding.protocol import EmbeddingResult
from app.core.constants import EMBEDDING_DIM

# 기록에 남을 이름. 나중에 DB 에서 "이건 가짜 벡터였다"를 골라낼 수 있어야 한다.
# document_chunks.embedding_model 로 조회하면 되고, ix_chunk_model 인덱스가
# (embedding_model, document_id) 라 이 이름으로 지우는 것이 빠르다.
FAKE_MODEL_NAME = "fake-hash-v1"


class FakeEmbeddingClient:
    """텍스트 해시로 결정적 단위 벡터를 만든다."""

    def __init__(self, dimension: int = EMBEDDING_DIM) -> None:
        if dimension <= 0:
            raise ValueError("dimension 은 0 보다 커야 한다")
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return FAKE_MODEL_NAME

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=tuple(self._vector(t) for t in texts),
            model=self.model_name,
            dimension=self._dimension,
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        return self.embed_documents([text])

    # --- 내부 ---------------------------------------------------------------

    def _vector(self, text: str) -> tuple[float, ...]:
        """SHA-256 을 반복 확장해 dimension 개의 float 를 만들고 정규화한다.

        해시 한 번은 32바이트(=float 32개)뿐이라 1024차원을 채우려면 여러 번
        돌려야 한다. 카운터를 붙여 이어 붙인다.
        """
        raw = bytearray()
        counter = 0
        seed = text.encode("utf-8")
        while len(raw) < self._dimension:
            raw.extend(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest())
            counter += 1

        # 바이트(0~255)를 -1.0 ~ 1.0 으로 옮긴다.
        values = [(b / 127.5) - 1.0 for b in raw[: self._dimension]]

        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0.0:
            # 이론상 거의 불가능하지만, 0 벡터는 코사인 거리가 정의되지 않는다.
            # pgvector 도 0 벡터에 대해 NaN 을 돌려주므로 막아 둔다.
            values = [1.0] + [0.0] * (self._dimension - 1)
            norm = 1.0
        return tuple(v / norm for v in values)

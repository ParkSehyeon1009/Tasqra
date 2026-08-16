# =============================================================================
# 이 파일의 책임: protocol.py 의 EmbeddingClientProtocol 을, Ollama 처럼
#   "OpenAI 호환" /v1/embeddings 를 제공하는 로컬 서버 호출로 구현한다.
#   임베딩 모델을 컨테이너 안에 올리지 않고 호스트 프로세스에 맡기는 것이
#   목적이다. 그래서 이 파일은 torch · sentence-transformers 를 쓰지 않고
#   이미 requirements.txt 에 있는 openai SDK 만 쓴다 — 새 의존성이 0 이다.
#
#   왜 이렇게 하나: api 와 worker 가 같은 Dockerfile 을 공유하므로
#   sentence-transformers(+torch) 를 넣으면 두 이미지가 함께 무거워지고,
#   두 컨테이너가 각각 약 2.3GB(BGE-M3 float32)를 메모리에 올린다. 개발
#   노트북에서 감당하기 어렵다. 호스트 서버에 한 번만 올려 두고 HTTP 로
#   부르면 컨테이너 메모리 증가가 0 이다.
#
# 다른 파일과의 관계: ai/local_client.py 의 LocalAIClient 와 짝이다. 차이는
#   (1) chat.completions 대신 embeddings 를 부르고
#   (2) AsyncOpenAI 가 아니라 동기 OpenAI 를 쓴다는 점이다.
#   동기인 이유는 protocol.py 주석에 적었다 — Celery 워커가 동기 코드다.
#   dependencies.get_embedding_client() 가 주입한다.
#
# !! 미검증 (2026-08-14 기준):
#   - 이 경로는 아직 실제 서버로 확인하지 못했다. 개발 노트북에 Ollama 가
#     설치되어 있지 않아서다(`ollama --version` 이 CommandNotFound).
#   - 우리 정확도 측정은 sentence-transformers · float32 · max_seq 1024 로 했다.
#     GGUF 양자화판을 쓰면 벡터가 달라지므로 그 수치를 그대로 쓸 수 없다.
#   - BGE-M3 의 dense 검색은 CLS 풀링 + 정규화다. GGUF 메타데이터의 풀링이
#     mean 으로 잡혀 있으면 에러 없이 조용히 품질이 떨어진다.
#   위 세 가지는 도구/embed-test 에서 재서 확인한 뒤에 실사용으로 넘겨야 한다.
#   그때까지 기본값은 FakeEmbeddingClient 다 (USE_FAKE_EMBEDDING=true).
# =============================================================================

from __future__ import annotations

from openai import OpenAI

from app.core.config import Settings
from app.embedding.protocol import EmbeddingResult


class LocalEmbeddingClient:
    """OpenAI 호환 /v1/embeddings 를 부른다."""

    provider = "local"

    def __init__(self, settings: Settings) -> None:
        self._model = settings.EMBEDDING_MODEL
        self._dimension = settings.EMBEDDING_DIM
        self._batch_size = settings.EMBEDDING_BATCH_SIZE
        self._client = OpenAI(
            base_url=settings.EMBEDDING_BASE_URL,
            # 로컬 서버는 인증하지 않지만 SDK 가 api_key 없이는 만들어지지 않는다.
            api_key=settings.API_KEY or "local",
            timeout=settings.EMBEDDING_TIMEOUT_SECONDS,
        )

    @property
    def model_name(self) -> str:
        # document_chunks.embedding_model 이 String(100) 이라 넘치면 DB 에서
        # 잘리거나 에러가 난다. 여기서 미리 자른다.
        return self._model[:100]

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), model=self.model_name, dimension=self._dimension)

        vectors: list[tuple[float, ...]] = []
        # 한 번에 다 보내면 서버가 메모리로 터지거나 타임아웃이 난다.
        # 청크는 문서 하나에 수백 개가 나오므로 반드시 나눠 보낸다.
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            response = self._client.embeddings.create(model=self._model, input=batch)
            # 서버가 순서를 바꿔 줄 수 있으므로 index 로 되돌린다. 순서가 어긋나면
            # 청크와 벡터가 서로 뒤바뀌어 저장되는데, 에러 없이 검색만 이상해진다.
            ordered = sorted(response.data, key=lambda item: item.index)
            for item in ordered:
                vector = tuple(float(v) for v in item.embedding)
                if len(vector) != self._dimension:
                    raise ValueError(
                        f"임베딩 차원이 맞지 않는다: 기대 {self._dimension}, "
                        f"실제 {len(vector)} (모델 {self._model}). "
                        "document_chunks 에 embedding_dim CHECK 제약이 있어 저장할 수 없다."
                    )
                vectors.append(vector)

        return EmbeddingResult(
            vectors=tuple(vectors), model=self.model_name, dimension=self._dimension
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        # BGE-M3 계열은 질의에 접두어를 붙이지 않는다. E5 계열로 바꾸면
        # 여기서 "query: " 를 붙이게 된다 — 서비스 코드는 그대로 둔다.
        return self.embed_documents([text])

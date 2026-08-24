# =============================================================================
# 이 파일의 책임: protocol.py 의 EmbeddingClientProtocol 을, 베이스 모델 +
#   파인튜닝 LoRA 어댑터를 **프로세스 안에서 직접 로드**해 구현한다.
#
# 다른 파일과의 관계: local_client.py(LocalEmbeddingClient) 와 짝이다. 차이는
#   모델을 HTTP 로 부르느냐(그쪽) 직접 올리느냐(이쪽)다. 둘 다 남겨 둔 이유는
#   운영 조건에 따라 고를 수 있게 하기 위해서다.
#     직접 로드 : 서버를 따로 안 띄워도 된다. 대신 컨테이너가 모델 메모리를 쓴다.
#     HTTP     : 컨테이너 메모리가 늘지 않는다. 대신 서버를 띄워 둬야 한다.
#   dependencies.get_embedding_client() 가 settings 를 보고 고른다.
#
# ⚠️ model_name 에 어댑터 이름을 함께 넣는다. 이 값이
#   document_chunks.embedding_model 에 기록되고, 검색이 "같은 모델로 만든 청크"
#   만 고르는 기준이 된다. 베이스 이름만 쓰면 **파인튜닝 전 벡터와 후 벡터가
#   구분되지 않아** 서로 다른 공간의 거리를 에러 없이 계산하게 된다.
#
# ⚠️ 어댑터는 저장소의 adapters/ 에 있다(각 27MB). 베이스 모델(2.2GB)은 첫
#   실행 때 HF 에서 받아 캐시된다. 캐시를 볼륨으로 잡지 않으면 컨테이너를
#   다시 만들 때마다 2.2GB 를 다시 받는다.
# =============================================================================

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path

from app.core.config import Settings
from app.embedding.protocol import EmbeddingResult

logger = logging.getLogger(__name__)


class LocalModelEmbeddingClient:
    """베이스 모델 + LoRA 어댑터를 직접 올려 임베딩한다."""

    provider = "local-model"

    def __init__(self, settings: Settings) -> None:
        self._base = settings.EMBEDDING_BASE_MODEL
        self._adapter = settings.EMBEDDING_ADAPTER_PATH
        self._dimension = settings.EMBEDDING_DIM
        self._batch_size = settings.EMBEDDING_BATCH_SIZE
        self._max_seq_length = settings.EMBEDDING_MAX_SEQ_LENGTH
        self._device = settings.MODEL_DEVICE or None

    @cached_property
    def _model(self):
        # 로딩이 무겁다(디스크에서 2.2GB). dependencies 의 lru_cache 덕에
        # 프로세스당 한 번이지만, 그마저도 첫 요청 때까지 미룬다.
        import torch
        from sentence_transformers import SentenceTransformer

        device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("임베딩 모델 로딩: %s (%s)", self._base, device)

        model = SentenceTransformer(self._base, device=device)

        if self._adapter:
            path = Path(self._adapter)
            if not path.is_absolute():
                # 저장소 루트(backend/) 기준으로 푼다. 컨테이너 WORKDIR 이 /app 이고
                # Dockerfile 이 adapters/ 를 그 아래로 복사한다.
                path = Path(__file__).resolve().parents[2] / self._adapter
            if not path.exists():
                raise RuntimeError(
                    f"어댑터를 찾을 수 없다: {path}\n"
                    "  EMBEDDING_ADAPTER_PATH 를 확인하거나, 어댑터 없이 베이스만\n"
                    "  쓰려면 빈 문자열로 두어라. 다만 검색 품질이 크게 떨어진다\n"
                    "  (문서 단위 k=5 기준 93.0% -> 64.0%)."
                )
            logger.info("어댑터 적용: %s", path)
            model.load_adapter(str(path))

        model.max_seq_length = self._max_seq_length

        # fp16 은 메모리를 절반으로 줄인다. CPU 에서는 연산이 오히려 느려질 수
        # 있어 GPU 일 때만 쓴다.
        if device == "cuda":
            model = model.half()

        return model

    @property
    def model_name(self) -> str:
        # ⚠️ 어댑터 이름을 함께 넣는다. 이 값으로 "같은 모델의 청크"를 고르므로
        #   파인튜닝 전/후가 구분되어야 한다.
        # String(100) 이라 넘치면 DB 에서 잘린다. 여기서 미리 자른다.
        name = self._base
        if self._adapter:
            name = f"{name}+{Path(self._adapter).name}"
        return name[:100]

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(
                vectors=(), model=self.model_name, dimension=self._dimension
            )

        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            # pgvector 의 <=> 는 코사인 거리다. 정규화해 두면 내적과 같아지고
            # search_service 의 `1 - distance = 유사도` 계산이 성립한다.
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        out: list[tuple[float, ...]] = []
        for vector in vectors:
            if len(vector) != self._dimension:
                raise ValueError(
                    f"임베딩 차원이 맞지 않는다: 기대 {self._dimension}, "
                    f"실제 {len(vector)} (모델 {self.model_name}). "
                    "document_chunks 에 embedding_dim CHECK 제약이 있어 저장할 수 없다."
                )
            out.append(tuple(float(v) for v in vector))

        return EmbeddingResult(
            vectors=tuple(out), model=self.model_name, dimension=self._dimension
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        # BGE-M3 계열은 질의에 접두어를 붙이지 않는다. E5 계열로 바꾸면
        # 여기서 "query: " 를 붙이게 된다 — 서비스 코드는 그대로 둔다.
        return self.embed_documents([text])

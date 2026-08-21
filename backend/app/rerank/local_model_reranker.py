# =============================================================================
# 이 파일의 책임: protocol.py 의 RerankerProtocol 을, 베이스 크로스 인코더 +
#   파인튜닝 LoRA 어댑터를 프로세스 안에서 직접 로드해 구현한다.
#   embedding/local_model_client.py 와 같은 구조다.
#
# ⚠️ **범용 리랭커를 그대로 쓰면 안 된다.** 실측에서 문서 단위 k=1 이
#   66.4%(리랭커 없이) → 37.9%(범용 리랭커) 로 반토막 났다. 우리 임베딩이
#   이 도메인에 파인튜닝돼 있어 범용 리랭커보다 강하기 때문이다.
#   adapters/reranker-v1 을 반드시 함께 쓸 것.
#
# ⚠️ **GPU 가 아니면 켜지 마라.** 후보 10건 재정렬에
#     GPU  527ms   /   CPU  8,511ms
#   CPU 에서는 검색 한 번에 8.5초다. 그럴 바에는 리랭커를 끄고 limit 을 10 으로
#   두는 편이 낫다 — 정확도가 97.2% 로 오히려 높고 검색이 50ms 다.
#     리랭커 N=10 → 상위 5개 : k=5 96.3%
#     리랭커 없이 상위 10개  : k=10 97.2%
#   리랭커가 사는 것은 정확도가 아니라 "LLM 에 넘길 청크 수" 다.
# =============================================================================

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LocalModelReranker:
    """베이스 크로스 인코더 + LoRA 어댑터를 직접 올려 재정렬한다."""

    provider = "local-model"

    def __init__(self, settings: Settings) -> None:
        self._base = settings.RERANK_BASE_MODEL
        self._adapter = settings.RERANK_ADAPTER_PATH
        self._batch_size = settings.RERANK_BATCH_SIZE
        self._max_seq_length = settings.RERANK_MAX_SEQ_LENGTH
        self._device = settings.MODEL_DEVICE or None

    @cached_property
    def _model(self):
        import torch
        from sentence_transformers.cross_encoder import CrossEncoder

        device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
        if device == "cpu":
            logger.warning(
                "리랭커가 CPU 에서 돕니다. 후보 10건에 약 8.5초가 걸려 검색이 "
                "사실상 멈춥니다. RERANK_ENABLED=false 를 권합니다."
            )
        logger.info("리랭커 로딩: %s (%s)", self._base, device)

        model = CrossEncoder(self._base, num_labels=1, device=device)

        if self._adapter:
            path = Path(self._adapter)
            if not path.is_absolute():
                path = Path(__file__).resolve().parents[2] / self._adapter
            if not path.exists():
                raise RuntimeError(
                    f"리랭커 어댑터를 찾을 수 없다: {path}\n"
                    "  범용 리랭커를 그대로 쓰면 검색이 오히려 나빠진다"
                    " (문서 단위 k=1 66.4% -> 37.9%).\n"
                    "  경로를 고치거나 RERANK_ENABLED=false 로 끄어라."
                )
            logger.info("어댑터 적용: %s", path)
            model.model.load_adapter(str(path))

        # 크로스 인코더는 질의와 문단을 **이어붙여** 넣으므로 같은 청크라도
        # bi-encoder 보다 긴 시퀀스가 된다. 질의 길이만큼 여유를 둔다.
        model.max_seq_length = self._max_seq_length
        return model

    @property
    def model_name(self) -> str:
        if self._adapter:
            return f"{self._base}+{Path(self._adapter).name}"
        return self._base

    def rerank(self, query: str, passages: list[str]) -> list[int]:
        if not passages:
            return []

        scores = self._model.predict(
            [(query, passage) for passage in passages],
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        order = sorted(range(len(passages)), key=lambda i: float(scores[i]), reverse=True)
        return order

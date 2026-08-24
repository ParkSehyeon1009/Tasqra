# 파인튜닝 LoRA 어댑터

공공 SI·용역 문서 검색에 맞춰 학습한 **LoRA 어댑터**다. 모델 전체가 아니라
베이스 모델과의 **차이분**만 담고 있어서 각각 27MB 다.

```
adapters/
├── embedding-hn-v1/    베이스: dragonkue/BGE-m3-ko
└── reranker-v1/        베이스: dragonkue/bge-reranker-v2-m3-ko
```

## ⚠️ 지금은 아직 쓰이지 않는다

이 커밋은 **파일만** 넣은 것이다. 이것을 로드하는 코드는 아직 없다.
현재 임베딩 경로는 `USE_FAKE_EMBEDDING` 에 따라 가짜 벡터이거나
`LocalEmbeddingClient`(OpenAI 호환 HTTP)다.

연결에 필요한 나머지는 별도로 진행한다:

- 베이스+어댑터를 로드하는 임베딩 클라이언트
- `SearchService` 에 리랭킹 단계 (현재 호출 지점 없음)
- `requirements.txt` 에 torch · sentence-transformers · peft
- `docker-compose.yml` 에 GPU 예약
- `Dockerfile` 에 이 폴더 COPY

## 쓰는 법 (연결된 뒤)

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("dragonkue/BGE-m3-ko")   # HF 에서 자동 다운로드
model.load_adapter("adapters/embedding-hn-v1")        # 이 저장소의 27MB
```

`SentenceTransformer` 와 `CrossEncoder` 둘 다 `load_adapter()` 를 기본 제공한다.
`peft` 가 설치돼 있어야 한다.

베이스 모델(각 2.2GB)은 첫 실행 때 HF 에서 자동으로 받아 캐시된다.
저장소에는 어댑터만 두는 이유가 이것이다 — 4.4GB 를 따로 호스팅할 필요가 없다.

## 왜 어댑터만 넣는가

| | 크기 | git |
|---|---|---|
| 병합된 모델 2개 | 4,332 MB | ✗ GitHub 단일 파일 100MB 제한 초과 |
| **어댑터 2개** | **54 MB** | **✓** |

git 은 바이너리 이력을 지울 수 없게 쌓는다. 모델을 넣으면 학습할 때마다
2.2GB 가 영구히 누적되고, 이후 clone 하는 모든 사람이 그것을 받는다.

## 성능 (학습 시점 측정)

평가셋: 공공 SI 입찰문서 30건 / 청크 1,339개 / 손으로 쓴 질의 214개.
**문서 단위로 검색 범위를 제한**한 조건 — 실서비스 조건이다.

| | k=1 | k=5 | k=10 |
|---|---|---|---|
| 베이스 (파인튜닝 전) | 24.3% | 64.0% | 82.2% |
| **어댑터 적용** | **66.4%** | **93.0%** | **97.2%** |
| 어댑터 + 리랭커 (N=10) | 70.1% | 96.3% | 97.2% |

### 알아둘 것

**검색 범위 제한이 가장 큰 레버다.** 같은 모델로 전체 코퍼스를 뒤지면 k=5 가
73.8% 인데 문서를 지정하면 93.0% 다. `document_id` 를 줄 수 있으면 반드시 줄 것.

**top-1 은 신뢰하면 안 된다.** k=1 이 66~70% 다. 1위만 보여주는 UI 를 만들면
30% 는 틀린 것을 보여준다. 상위 5개를 LLM 에 넘기는 방식이 맞다.

**리랭커는 GPU 가 필요하다.** CPU 에서 검색 1회에 8.5초다 (GPU 527ms 의 16배).
GPU 를 쓸 수 없으면 리랭커를 끄고 top_k 를 10 으로 두는 편이 낫다 —
정확도가 97.2% 로 오히려 높고 검색이 50ms 다.

## ⚠️ 임베딩 모델을 바꾸면 전체 재색인이 필요하다

기존 벡터는 다른 공간의 값이라 무효가 된다. 섞이면 거리 계산이 **에러 없이**
무의미해진다. `document_chunks.embedding_model` 과 `ix_chunk_model` 인덱스로
옛 모델 청크만 골라 지우고 다시 만들 것.

## 재현·갱신

학습과 어댑터 추출은 `MainProject/AgentLearning` 에서 한다 (저장소 밖).
실험 산출물을 본프로젝트에 섞지 않으려고 분리했다.

```bash
# 어댑터 추출 (병합된 모델 → 어댑터, 재학습 불필요)
python src/extract_adapter.py --merged outputs/adapter-hn-e36 \
    --base dragonkue/BGE-m3-ko --out adapters/embedding-hn-v1
```

추출 스크립트는 검증 3단계를 출력한다. **재구성 결과가 원본과 같은지
(코사인 1.000000) 확인하고 교체할 것.**

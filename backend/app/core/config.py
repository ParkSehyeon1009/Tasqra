# =============================================================================
# 이 파일의 책임: 환경 변수(.env)를 읽어 타입이 보장된 설정 객체로 노출한다.
# 다른 파일과의 관계: main.py(CORS 설정, DB 연결), ai/openai_client.py(API_KEY),
#   db/session.py(DATABASE_URL), dependencies.py(USE_FAKE_AI) 등
#   설정값이 필요한 모든 곳에서 이 모듈의 settings 인스턴스를 import해서 쓴다.
# Spring 비교: application.yml + @ConfigurationProperties 클래스와 동일한 역할.
#   차이점은, Spring은 프로필(yml)을 쓰지만 여기서는 .env 파일 + Pydantic
#   BaseSettings가 "타입 검증 + 환경변수 바인딩"을 동시에 해준다.
# 참고: pydantic-settings는 기본적으로 .env 파일에 모델에 선언되지 않은 키가
#   있으면 검증 에러(extra_forbidden)를 던진다. 그래서 .env.example에 새 키를
#   추가할 때는 반드시 이 클래스에도 짝이 되는 필드를 추가해야 한다.
# =============================================================================

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: str
    ENVIRONMENT: str
    CORS_ORIGINS: str

    # --- DB (docker-compose의 postgres 서비스와 짝을 맞춘다) --------------------
    DATABASE_URL: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # --- AI 클라이언트 -----------------------------------------------------
    # USE_FAKE_AI 기본값은 반드시 True로 둔다 — 개발 중 실수로 실제 OpenAI API가
    # 호출되어 비용이 발생하는 것을 막기 위한 안전장치이다 (dependencies.py에서 사용).
    USE_FAKE_AI: bool = True
    # USE_FAKE_AI=false일 때 어떤 제공자를 쓸지 고른다.
    #   "openai" -> 상용 OpenAI API
    #   "local"  -> Ollama 등 OpenAI 호환 로컬 서버 (호출 비용 없음)
    AI_PROVIDER: str = "openai"
    # AI_PROVIDER=local일 때 호출할 로컬 서버 주소.
    #   venv에서 직접 실행: http://localhost:11434/v1
    #   도커 컨테이너 안:   http://host.docker.internal:11434/v1
    #   (컨테이너의 localhost는 컨테이너 자신이라 호스트에 닿지 않는다)
    AI_BASE_URL: str = "http://localhost:11434/v1"
    AI_MODEL: str
    # ⚠️ 2026-08-28: 요약과 분류를 **다른 모델**로 부른다.
    #   LoRA 어댑터를 태스크별로 따로 학습했고, 어댑터 둘을 GGUF 하나로 합칠
    #   수 없다 — 각각 베이스에 병합되어 별개 모델이 된다.
    #
    #     AI_MODEL_SUMMARY   Tasqra-summation       요약 (2~3문장 200자)
    #     AI_MODEL_CATEGORY  Tasqra-classification  분류 (8종 코드)
    #
    #   비워 두면 AI_MODEL 을 쓴다. 개발 중 하나만 올려놓고 돌릴 때를 위해서다.
    #   ⚠️ 다만 그 경우 한쪽 태스크는 다른 태스크용으로 학습된 어댑터가 처리하게
    #     되어 성능이 떨어진다. 운영에서는 둘 다 지정할 것.
    AI_MODEL_SUMMARY: str = ""
    AI_MODEL_CATEGORY: str = ""
    AI_TIMEOUT_SECONDS: int
    # 원문 한 구간의 문자 상한. 실제 요청은 메시지·출력 여유를 포함한
    # 보수적인 UTF-8 byte 예산도 함께 검사한다. 요약은 원문 전체를 분할 처리한다.
    AI_MAX_INPUT_CHARS: int = Field(default=6000, ge=256)
    # 로컬 서버의 실제 컨텍스트 설정과 맞춰야 한다. 서버 설정을 바꾸는 값은 아니다.
    AI_CONTEXT_TOKENS: int = Field(default=8192, ge=2048)
    AI_MAX_OUTPUT_TOKENS: int = Field(default=1536, ge=256)
    AI_CHUNK_OVERLAP_CHARS: int = Field(default=160, ge=0)
    AI_MAX_CHUNKS: int = Field(default=256, ge=1)
    AI_CHUNK_RETRIES: int = Field(default=1, ge=0, le=2)
    AI_ANALYSIS_TIMEOUT_SECONDS: int = Field(default=1800, ge=60)

    # --- 임베딩 (RAG-001-1 청킹 · RAG-001-2 임베딩) --------------------------------
    # USE_FAKE_EMBEDDING 기본값은 반드시 True로 둔다 — USE_FAKE_AI와 같은 이유의
    # 안전장치다. 다만 막는 대상이 "비용"이 아니라 "메모리"다. 실제 임베딩 모델
    # (BGE-M3 float32)은 약 2.3GB를 잡고, api와 worker가 각각 올리면 약 4.6GB다.
    # 개발 노트북에서 이것이 켜진 줄 모르고 있으면 스왑으로 밀려 아주 느려진다.
    USE_FAKE_EMBEDDING: bool = True
    # USE_FAKE_EMBEDDING=false 일 때 어떤 구현을 쓸지 고른다.
    #   "local-model" -> 컨테이너 안에서 모델을 직접 로드 (서버 불필요)
    #   "local-http"  -> OpenAI 호환 /v1/embeddings 서버 호출 (컨테이너 메모리 0)
    # 직접 로드는 서버를 안 띄워도 되는 대신 컨테이너가 모델 메모리를 쓴다
    # (fp16 기준 약 1.2GB). 어느 쪽이 나은지는 운영 조건에 달렸다.
    EMBEDDING_PROVIDER: str = "local-model"
    # document_chunks.embedding_model 에 기록되는 이름이자, 로컬 서버에 넘기는
    # 모델 이름이다. 모델을 바꾸면 ix_chunk_model 인덱스로 "이 모델로 만든
    # 청크"만 골라 지우고 다시 만든다.
    EMBEDDING_MODEL: str = "dragonkue/BGE-m3-ko"
    # models/chunk.py 의 EMBEDDING_DIM 과 반드시 같아야 한다. document_chunks 에
    # embedding_dim = 1024 CHECK 제약이 걸려 있어 다르면 INSERT 가 실패한다.
    # BGE-m3-ko · KURE-v1 · snowflake-arctic-embed-l-v2.0 이 모두 1024다.
    EMBEDDING_DIM: int = 1024
    # OpenAI 호환 /v1/embeddings 주소. 컨테이너 안에서는 host.docker.internal 로
    # 호스트를 봐야 한다 (컨테이너의 localhost는 컨테이너 자신이다).
    EMBEDDING_BASE_URL: str = "http://localhost:11434/v1"
    EMBEDDING_TIMEOUT_SECONDS: int = 120
    # 한 번의 요청에 넣을 청크 수. 너무 크면 서버가 타임아웃하거나 메모리로 터진다.
    EMBEDDING_BATCH_SIZE: int = 16

    # --- 직접 로드용 (EMBEDDING_PROVIDER="local-model") ------------------------
    # 베이스 모델. 첫 실행 때 HF 에서 받아 캐시된다(약 2.2GB).
    EMBEDDING_BASE_MODEL: str = "dragonkue/BGE-m3-ko"
    # 파인튜닝 LoRA 어댑터. 저장소의 adapters/ 에 들어 있다(27MB).
    # ⚠️ 비우면 베이스만 쓰는데, 검색 품질이 크게 떨어진다
    #   (문서 단위 k=5 기준 93.0% -> 64.0%).
    EMBEDDING_ADAPTER_PATH: str = "adapters/embedding-hn-v1"
    # 토큰 상한. 학습·측정을 이 값으로 했으므로 바꾸면 성능이 달라진다.
    # 우리 청크의 p95 가 515토큰이라 512 면 5% 만 잘린다.
    EMBEDDING_MAX_SEQ_LENGTH: int = 512

    # --- 리랭킹 (검색 후보 재정렬) ---------------------------------------------
    # ⚠️ **GPU 가 아니면 켜지 마라.** 후보 10건 재정렬에 GPU 527ms / CPU 8,511ms 다.
    #   CPU 에서는 검색 한 번에 8.5초가 되어 사실상 멈춘다.
    #   끄고 SEARCH limit 을 10 으로 두는 편이 낫다 — 문서 단위 k=10 이 97.2% 로
    #   리랭커를 켠 k=5(96.3%)보다 오히려 높다.
    #   리랭커가 사는 것은 정확도가 아니라 "LLM 에 넘길 청크 수" 다(10개 -> 5개).
    RERANK_ENABLED: bool = False
    RERANK_BASE_MODEL: str = "dragonkue/bge-reranker-v2-m3-ko"
    # ⚠️ 범용 리랭커를 그대로 쓰면 검색이 **나빠진다** (문서 단위 k=1 66.4% -> 37.9%).
    #   우리 임베딩이 이 도메인에 파인튜닝돼 있어 범용 리랭커보다 강해서다.
    #   반드시 이 어댑터를 함께 쓸 것.
    RERANK_ADAPTER_PATH: str = "adapters/reranker-v1"
    # 재정렬에 넘길 후보 수. 실측(문서 단위):
    #   N=10  k=5 96.3%  527ms   <- 채택
    #   N=20  k=5 97.2%  901ms   (+0.9%p 에 지연 71% 증가)
    RERANK_CANDIDATE_POOL: int = 10
    RERANK_BATCH_SIZE: int = 16
    # 질의와 문단을 이어붙여 넣으므로 임베딩보다 길게 잡는다.
    RERANK_MAX_SEQ_LENGTH: int = 576

    # 모델을 올릴 장치. 비우면 CUDA 가 있으면 CUDA, 없으면 CPU 로 자동 선택한다.
    # 강제하려면 "cuda" 또는 "cpu".
    MODEL_DEVICE: str = ""

    # --- 의미 검색 (SRH-001) --------------------------------------------------
    # HNSW 가 한 번에 꺼내 오는 후보 수. pgvector 기본값은 40인데, project_id 와
    # embedding_model 조건이 걸린 상황에서는 40개 중 조건을 통과하는 것이 적어
    # 결과가 모자란다. iterative_scan 이 부족분을 더 꺼내 오지만, 처음부터
    # 넉넉히 두면 반복 횟수가 줄어든다. 올릴수록 정확하고 느려진다.
    SEARCH_EF_SEARCH: int = 100
    # 검색 결과에 담을 원문 인용 길이(글자). 청크는 최대 480토큰이라 전문을
    # 담으면 목록 응답이 커진다. 프론트가 char_count 와 비교해 잘렸는지 안다.
    SEARCH_SNIPPET_CHARS: int = 220

    # --- 키워드 검색 (SRH-003) -----------------------------------------------
    # 검색어 최소 길이. 트라이그램은 글자 3개씩 만들므로 3글자 미만이면
    # ix_chunk_text_trgm 인덱스를 쓸 수 없고 순차 스캔으로 떨어진다.
    #
    # 그래도 2 로 두는 이유: "제1조" · "SI" · "VAT" 같은 실제 검색어가 짧다.
    # 1글자는 막는다 — 어느 청크에나 있어서 결과가 사실상 전체가 된다.
    SEARCH_KEYWORD_MIN_LENGTH: int = 2
    # 키워드 결과의 원문 인용 길이(글자). 의미 검색보다 좁게 둔다 — 의미 검색은
    # 청크의 주제를 보여주려고 앞부분을 주지만, 키워드는 "찾은 그 자리"를
    # 보여주는 것이 목적이라 매치 주변만 있으면 된다.
    SEARCH_KEYWORD_SNIPPET_CHARS: int = 160

    # --- 하이브리드 검색 (SRH-004) -------------------------------------------
    # 두 방식에서 각각 몇 개를 후보로 가져올까. 최종 limit 보다 넉넉해야 한다 —
    # 한쪽에만 걸린 정답이 합친 순위에서 밀려 잘리는 것을 막는다.
    #
    # 이 값이 곧 **리랭커(SRH-002-1)의 상한을 정한다.** 리랭커는 받은 후보 안에서
    # 순서만 바꾸므로, 후보에 없는 정답은 어떤 리랭커도 못 올린다.
    # 인수인계 9-G ⑤ 의 상한 표가 이 수와 짝이다.
    SEARCH_HYBRID_CANDIDATES: int = 30
    # --- 프롬프트 컨텍스트 조립 (RAG-002-1) ----------------------------------
    # LLM 프롬프트에 근거로 담을 토큰 예산. 모델의 컨텍스트 창 전체가 아니라
    # **근거 자료 몫**이다. 지시문·질문·답변 몫은 여기 포함되지 않으므로,
    # 모델 창이 8k 라도 이 값을 8k 로 두면 안 된다.
    #
    # 청크 하나가 최대 480토큰(CHUNK_MAX_TOKENS)이므로 4,000 이면 근거 8개가
    # 들어간다. 검색 결과 상위 몇 개를 근거로 쓸지와 함께 봐야 한다.
    CONTEXT_BUDGET_TOKENS: int = 4000
    # 근거 개수 상한. 예산이 남아도 이보다 많이 담지 않는다.
    #
    # 근거가 너무 많으면 LLM 이 무엇을 인용할지 흐려지고("lost in the middle"),
    # 사용자도 출처를 확인하기 어렵다. 예산과 개수를 함께 거는 이유다.
    CONTEXT_MAX_EVIDENCES: int = 8

    # RRF(Reciprocal Rank Fusion)의 완충 상수. 점수 = Σ 1/(k + 순위).
    #
    # 60 은 RRF 를 제안한 논문(Cormack 외, 2009)이 쓴 값이고 이후 사실상 기본값이
    # 되었다. 클수록 1등과 10등의 차이가 줄어(순위 차이를 덜 신뢰), 작을수록
    # 1등에 크게 쏠린다. 우리 데이터로 재기 전에는 통용값을 쓴다.
    SEARCH_HYBRID_RRF_K: int = 60

    # --- 청킹 규칙 (services/chunking.py 의 기본값을 환경에서 덮어쓴다) --------
    # 임베딩 모델에 넣는 청크 하나의 최대 토큰 수. 우리 정확도 측정을
    # max_seq_length=1024 로 했으므로 그 안에 들어와야 측정값을 그대로 쓸 수 있다.
    #
    # 이 값은 chunking.py 의 CHARS_PER_TOKEN(1.89, 실측) 과 짝이다. 둘을 곱한
    # 값이 청크의 최대 글자 수(480 x 1.89 = 907자)이고, 그것이 실제 토큰으로
    # max_seq_length 를 넘으면 모델이 뒤를 조용히 잘라낸다. 에러가 없어서
    # 알아채기 어렵다. 그래서 이 값을 올릴 때는 CHARS_PER_TOKEN 과
    # embed_server.py 의 max_seq 를 함께 봐야 한다.
    CHUNK_MAX_TOKENS: int = 480
    # 이보다 짧은 청크는 다음 청크와 합친다. 제목 한 줄만 든 청크를 막는다.
    #
    # CHARS_PER_TOKEN 과 곱해져 실제로는 "몇 자 미만을 흡수하는가"로 동작한다
    # (30 x 1.89 = 57자). 그래서 비율을 고치면 이 값도 같이 봐야 한다. 이전 값
    # 48 은 잘못된 비율 1.2 를 전제로 맞춰진 것이어서, 비율만 고쳤을 때 흡수
    # 기준이 91자로 넓어져 짧은 절이 삼켜지는 회귀가 났다.
    CHUNK_MIN_TOKENS: int = 30
    # 앞 청크의 끝을 다음 청크에 얼마나 겹쳐 넣을지. 0 이면 겹치지 않는다.
    CHUNK_OVERLAP_TOKENS: int = 48

    # --- 업로드/추출 제약 ----------------------------------------------------
    UPLOAD_DIR: str
    MAX_FILE_SIZE_MB: int
    MAX_PAGES: int
    MAX_EXTRACTED_CHARS: int = 45_000
    # PaddleOCR 텍스트 검출 입력의 긴 변 상한. 원본·검수 이미지는 유지하고
    # 검출 단계에서만 비율을 보존해 축소한다.
    OCR_TEXT_DET_MAX_SIDE_LEN: int = 2_500

    # --- Background document processing ---------------------------------
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="UTF-8")

    @property
    def cors_origins_list(self) -> list[str]:
        return self.CORS_ORIGINS.split(",")

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def refresh_cookie_secure(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


settings = Settings()

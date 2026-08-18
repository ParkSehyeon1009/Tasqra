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
    AI_TIMEOUT_SECONDS: int
    # 프롬프트에 실어 보낼 문서 텍스트의 최대 길이. 로컬 소형 모델은 컨텍스트
    # 창이 좁아(Ollama 기본 num_ctx=2048) 긴 문서를 조용히 잘라먹으므로,
    # 어디까지 반영됐는지 예측 가능하도록 보내기 전에 명시적으로 자른다.
    AI_MAX_INPUT_CHARS: int = 6000

    # --- 임베딩 (RAG-01 청킹 · RAG-02 임베딩) --------------------------------
    # USE_FAKE_EMBEDDING 기본값은 반드시 True로 둔다 — USE_FAKE_AI와 같은 이유의
    # 안전장치다. 다만 막는 대상이 "비용"이 아니라 "메모리"다. 실제 임베딩 모델
    # (BGE-M3 float32)은 약 2.3GB를 잡고, api와 worker가 각각 올리면 약 4.6GB다.
    # 개발 노트북에서 이것이 켜진 줄 모르고 있으면 스왑으로 밀려 아주 느려진다.
    USE_FAKE_EMBEDDING: bool = True
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

    # --- 의미 검색 (RAG-04) --------------------------------------------------
    # HNSW 가 한 번에 꺼내 오는 후보 수. pgvector 기본값은 40인데, project_id 와
    # embedding_model 조건이 걸린 상황에서는 40개 중 조건을 통과하는 것이 적어
    # 결과가 모자란다. iterative_scan 이 부족분을 더 꺼내 오지만, 처음부터
    # 넉넉히 두면 반복 횟수가 줄어든다. 올릴수록 정확하고 느려진다.
    SEARCH_EF_SEARCH: int = 100
    # 검색 결과에 담을 원문 인용 길이(글자). 청크는 최대 480토큰이라 전문을
    # 담으면 목록 응답이 커진다. 프론트가 char_count 와 비교해 잘렸는지 안다.
    SEARCH_SNIPPET_CHARS: int = 220

    # --- 청킹 규칙 (services/chunking.py 의 기본값을 환경에서 덮어쓴다) --------
    # 임베딩 모델에 넣는 청크 하나의 최대 토큰 수. 우리 정확도 측정을
    # max_seq_length=1024 로 했으므로 그 안에 들어와야 측정값을 그대로 쓸 수 있다.
    CHUNK_MAX_TOKENS: int = 480
    # 이보다 짧은 청크는 다음 청크와 합친다. 제목 한 줄만 든 청크를 막는다.
    CHUNK_MIN_TOKENS: int = 48
    # 앞 청크의 끝을 다음 청크에 얼마나 겹쳐 넣을지. 0 이면 겹치지 않는다.
    CHUNK_OVERLAP_TOKENS: int = 48

    # --- 업로드/추출 제약 ----------------------------------------------------
    UPLOAD_DIR: str
    MAX_FILE_SIZE_MB: int
    MAX_PAGES: int
    MAX_EXTRACTED_CHARS: int = 45_000

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

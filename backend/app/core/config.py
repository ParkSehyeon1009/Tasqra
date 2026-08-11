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
    AI_MODEL: str
    AI_TIMEOUT_SECONDS: int

    # --- 업로드/추출 제약 ----------------------------------------------------
    UPLOAD_DIR: str
    MAX_FILE_SIZE_MB: int
    MAX_PAGES: int
    MAX_EXTRACTED_CHARS: int = 45_000

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

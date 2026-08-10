# =============================================================================
# 이 파일의 책임: FastAPI 애플리케이션을 조립(assemble)하는 진입점(entrypoint).
#   앱 인스턴스 생성, CORS, 전역 예외 핸들러, 미들웨어, DB 스키마 생성(lifespan),
#   (추후) 라우터를 한 곳에서 등록한다. 이 파일 자체에는 비즈니스 로직이 없다
#   — 오직 "배선(wiring)"만 한다.
# 다른 파일과의 관계: core/config.py(settings), core/exceptions.py(핸들러 3종),
#   core/middleware.py(RequestIdMiddleware), core/logging_config.py(setup_logging),
#   db/base.py + db/session.py(테이블 생성)를 모두 가져와 app에 연결한다.
#   도메인 라우터가 정해지면 api/routes/*.py를 include_router()로 추가한다.
# Spring 비교: Application.java(@SpringBootApplication) + WebMvcConfigurer +
#   @RestControllerAdvice 등록을 한 곳에 모아둔 것과 비슷합니다. Spring은
#   컴포넌트 스캔/어노테이션으로 자동 등록되지만, FastAPI/Starlette는 이렇게
#   명시적으로 app.add_middleware(...), app.add_exception_handler(...) 를 호출해야 합니다.
# =============================================================================

from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  # Base.metadata에 엔티티를 등록하기 위해 반드시 import 필요
from app.core.config import settings
from app.core.exceptions import (
    BusinessError,
    business_error_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from app.core.logging_config import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.db.base import Base
from app.db.session import engine

# 로깅 설정은 앱 인스턴스를 만들기 전에 먼저 초기화한다.
# (Spring에서 logback-spring.xml이 컨텍스트 로딩보다 먼저 적용되는 것과 같은 순서 이유)
setup_logging()
logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Alembic을 도입하지 않으므로(§ 하지 말아야 할 것) create_all()이 유일한
    # 스키마 동기화 수단이다. Spring의 JPA `ddl-auto: update`와 유사한 역할.
    # 로컬에서 아직 docker-compose(DB)를 안 띄운 경우에도 앱 자체는 뜨게 하고
    # 경고 로그만 남긴다 — DB 없이도 /health, /docs는 확인할 수 있어야 하므로.
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        logger.warning("DB에 연결할 수 없어 테이블 생성을 건너뜁니다. DB 연결 설정을 확인하세요.", exc_info=True)
    yield


app = FastAPI(lifespan=lifespan)

# --- CORS 설정 -----------------------------------------------------------
# 프론트 개발 서버(예: http://localhost:3000, http://localhost:5173 등)에서의
# 요청을 허용한다. 실제 허용 origin 목록은 core/config.py의 settings.CORS_ORIGINS
# (.env에서 읽어옴)를 그대로 사용한다 — 코드에 도메인을 하드코딩하지 않기 위함.
# Spring의 WebMvcConfigurer.addCorsMappings(...) 와 동일한 역할.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- request_id 미들웨어 등록 ---------------------------------------------
# 모든 요청에 request_id를 부여해 로그 추적 및 에러 응답에 사용한다.
# Spring의 OncePerRequestFilter를 FilterChain에 등록하는 것과 동일한 지점.
app.add_middleware(RequestIdMiddleware)

# --- 전역 예외 핸들러 등록 -------------------------------------------------
# Spring의 @RestControllerAdvice가 여러 @ExceptionHandler를 한 클래스에 모아두는 것과
# 달리, FastAPI에서는 (예외 타입, 핸들러 함수) 쌍을 하나씩 등록한다.
app.add_exception_handler(BusinessError, business_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


# --- 헬스체크 --------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --- 라우터 등록 자리 -------------------------------------------------------
# 담당자가 각자 라우터 파일(app/api/routes/*.py)을 만든 뒤 아래 두 줄(해당 담당자 분)의
# 주석을 해제하세요. 아직 파일이 없는 상태로 import하면 앱이 뜨지 않습니다.
from app.api.routes import upload_router      # 담당자 A: POST /api/documents
from app.api.routes import analysis_router    # 담당자 B: POST /api/documents/{id}/analyze
from app.api.routes import document_router    # 담당자 C: GET /api/documents, /{id}, /download, DELETE
app.include_router(upload_router.router)
app.include_router(analysis_router.router)
app.include_router(document_router.router)

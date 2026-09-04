from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.api.routes import amount_router, analysis_router, auth_router, chat_router, dashboard_router, decision_schedule_router, deliverable_router, document_router, invitation_router, project_router, search_router, task_router, upload_router
from app.core.config import settings
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import BusinessError, business_error_handler, http_exception_handler, unhandled_exception_handler, validation_error_handler
from app.core.logging_config import setup_logging
from app.core.middleware import RequestIdMiddleware

setup_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RequestIdMiddleware)
app.add_exception_handler(BusinessError, business_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
# 없는 경로(404)·허용되지 않은 메서드(405)는 라우터가 낸다. 이 핸들러가 없으면
# FastAPI 기본 형식({"detail": ...})으로 나가 code·request_id 가 빠진다.
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

app.include_router(auth_router.router)
app.include_router(project_router.router)
app.include_router(task_router.router)
app.include_router(invitation_router.router)
app.include_router(upload_router.router)
app.include_router(analysis_router.router)
app.include_router(document_router.router)
# 의미 검색(SRH-001). 담당 보현. 계약은 API_계약서.md 에 초안으로 추가했다.
app.include_router(search_router.router)
# 단일 프로젝트 문서 기반 질의응답 챗봇(CHAT-001). 검색 범위 정책과 실제
# 청크 전문을 재사용하고, 답변 근거는 서버가 조립 결과에서 매핑한다.
app.include_router(chat_router.router)
app.include_router(amount_router.router)
app.include_router(decision_schedule_router.router)
# 프로젝트 핵심 현황(DSH-001). 열린 태스크는 tasks 테이블에서 완료되지 않은
# TODO · IN_PROGRESS 항목을 집계한다.
app.include_router(dashboard_router.router)
app.include_router(dashboard_router.portfolio_router)
# 산출물 생성 대상 미리보기(DLV-001-2). 담당 보현. 만들기(POST)는 아직 없다 —
# 완료 판정이 "LLM 호출 전에 건수가 보인다" 이므로 미리보기를 먼저 낸다.
app.include_router(deliverable_router.router)

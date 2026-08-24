from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.api.routes import amount_router, analysis_router, auth_router, dashboard_router, deliverable_router, document_router, invitation_router, project_router, search_router, task_router, upload_router
from app.core.config import settings
from app.core.exceptions import BusinessError, business_error_handler, unhandled_exception_handler, validation_error_handler
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
app.include_router(amount_router.router)
# 프로젝트 핵심 현황(DSH-001). 담당 보현. 되는 지표만 — 열린 태스크는 tasks 테이블이
# 아직 없어서 세지 않는다(태스크 CRUD TSK-001-1 미구현, 담당 재정. open_tasks = null).
# decisions 가 아니다. 그 테이블은 리비전 0007 로 있고 ORM 모델만 없으며, 뜻도
# "결정사항" 이라 승인 대기 쪽이다. 자세한 근거는 schemas/dashboard.py 머리 주석.
app.include_router(dashboard_router.router)
# 산출물 생성 대상 미리보기(DLV-001-2). 담당 보현. 만들기(POST)는 아직 없다 —
# 완료 판정이 "LLM 호출 전에 건수가 보인다" 이므로 미리보기를 먼저 낸다.
app.include_router(deliverable_router.router)

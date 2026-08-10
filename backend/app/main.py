from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware

import app.models  # noqa: F401
from app.api.routes import analysis_router, auth_router, document_router, project_router, upload_router
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
app.include_router(upload_router.router)
app.include_router(analysis_router.router)
app.include_router(document_router.router)

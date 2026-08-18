# =============================================================================
# 이 파일의 책임: FastAPI Depends()로 주입할 객체들을 한 곳에서 조립한다.
#   (1) AI 클라이언트: settings.USE_FAKE_AI에 따라 FakeAIClient/OpenAIClient 선택.
#   (2) Repository: Depends(get_db)로 받은 세션을 감싸 생성.
#   (3) Extractor/Analyzer 레지스트리: 확장자/분석기 타입 -> 구현체 매핑.
#   담당자 A/B/C가 pdf/docx/hwpx/ocr extractor, summary/category analyzer를
#   완성하면, 아래 TODO 표시된 자리에 register()만 추가하면 된다 (§2-3).
# 다른 파일과의 관계: api/routes/*.py(라우터, 담당자 A/B/C가 구현)가 이 모듈의
#   함수들을 Depends(...)로 가져다 쓴다. services/*.py 생성자에도 이 함수들의
#   반환값이 주입된다.
# Spring 비교: Spring의 @Configuration + @Bean 메서드 모음과 같은 위치.
#   Spring은 @Profile("fake")/@ConditionalOnProperty로 구현체를 스위칭하지만,
#   여기서는 settings.USE_FAKE_AI 값을 보고 if/else로 직접 선택한다.
# =============================================================================

from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.ai.client_protocol import AIClientProtocol
from app.ai.fake_client import FakeAIClient
from app.ai.local_client import LocalAIClient
from app.ai.openai_client import OpenAIClient
from app.analyzers.category_analyzer import CategoryAnalyzer
from app.analyzers.protocol import Analyzer
from app.analyzers.summary_analyzer import SummaryAnalyzer
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.embedding.fake_client import FakeEmbeddingClient
from app.embedding.local_client import LocalEmbeddingClient
from app.embedding.protocol import EmbeddingClientProtocol
from app.extractors.docx_extractor import DocxExtractor
from app.extractors.fake_extractor import FakeExtractor
from app.extractors.hwpx_extractor import HwpxExtractor
from app.extractors.image_extractor import ImageExtractor
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.pdf_extractor import PdfExtractor
from app.extractors.registry import ExtractorRegistry
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.models.enums import MemberRole
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.project_service import ProjectService
from app.services.analysis_service import AnalysisService
from app.services.chunking_service import ChunkingService
from app.services.extraction_service import ExtractionService
from app.services.search_service import SearchService
from app.services.document_service import DocumentService

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    member: ProjectMember



@lru_cache
def get_ai_client() -> AIClientProtocol:
    # USE_FAKE_AI 기본값은 True — 개발 중 실수로 실제 API가 호출되어 비용이
    # 발생하는 것을 막기 위한 안전장치다. 실제 호출은 .env에서 명시적으로
    # USE_FAKE_AI=false로 바꿔야만 일어난다.
    if settings.USE_FAKE_AI:
        return FakeAIClient()
    # 로컬(Ollama 등 OpenAI 호환) 서버는 호출 비용이 없으므로 USE_FAKE_AI를
    # 끈 뒤 AI_PROVIDER=local로 두고 쓴다. 상용 API 호출은 AI_PROVIDER=openai일
    # 때만 일어난다.
    if settings.AI_PROVIDER.lower() == "local":
        return LocalAIClient(settings)
    return OpenAIClient(settings)


@lru_cache
def get_embedding_client() -> EmbeddingClientProtocol:
    # USE_FAKE_EMBEDDING 기본값은 True — get_ai_client()의 USE_FAKE_AI와 같은
    # 안전장치인데, 막는 대상이 비용이 아니라 메모리다. 실제 임베딩 모델
    # (BGE-M3 float32)은 약 2.3GB를 잡는다. lru_cache로 프로세스당 한 번만
    # 만드는 것도 그래서다 — uvicorn --reload 환경에서 매번 다시 만들면 못 쓴다.
    if settings.USE_FAKE_EMBEDDING:
        return FakeEmbeddingClient(dimension=settings.EMBEDDING_DIM)
    # 실제 경로는 OpenAI 호환 /v1/embeddings 서버(Ollama 등)를 부른다.
    # 컨테이너 안에 모델을 올리지 않으므로 이미지와 메모리가 늘지 않는다.
    return LocalEmbeddingClient(settings)


def get_chunk_repository(db: Session = Depends(get_db)) -> ChunkRepository:
    return ChunkRepository(db)


def get_chunking_service(
    db: Session = Depends(get_db),
    chunk_repository: ChunkRepository = Depends(get_chunk_repository),
) -> ChunkingService:
    return ChunkingService(
        db=db,
        chunk_repository=chunk_repository,
        embedding_client=get_embedding_client(),
    )


@lru_cache
def get_ocr_extractor() -> OcrExtractor:
    # PaddleOCR은 모델 로딩 비용이 크므로 업로드 추출 파이프라인에서
    # 같은 인스턴스를 재사용하도록 별도 provider로 둔다.
    return OcrExtractor()


@lru_cache
def get_extractor_registry() -> ExtractorRegistry:
    registry = ExtractorRegistry()

    ocr = get_ocr_extractor()
    image_extractor = ImageExtractor(ocr)

    registry.register("pdf", PdfExtractor(ocr))
    registry.register("docx", DocxExtractor(ocr))
    registry.register("hwpx", HwpxExtractor(ocr))
    registry.register("png", image_extractor)
    registry.register("jpg", image_extractor)
    registry.register("jpeg", image_extractor)
    # 참고/개발용 fake 타입은 그대로 유지한다.
    registry.register("fake", FakeExtractor())
    return registry


@lru_cache
def get_analyzer_registry() -> dict[str, Analyzer]:
    ai_client = get_ai_client()
    registry: dict[str, Analyzer] = {
        "summary": SummaryAnalyzer(ai_client),
        "category": CategoryAnalyzer(ai_client),
    }
    return registry


def get_document_repository(db: Session = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(db)


def get_analysis_repository(db: Session = Depends(get_db)) -> AnalysisRepository:
    return AnalysisRepository(db)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_project_repository(db: Session = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(db)


# get_search_service 는 get_project_repository 아래에 두어야 한다.
# Depends(get_project_repository) 는 기본값이라 **함수를 정의하는 순간** 평가된다.
# 위에 두면 임포트할 때 NameError 가 나고 앱이 아예 뜨지 않는다.
# 실제로 그렇게 해서 api 컨테이너가 죽었다 — 문법 오류가 아니라 이름 해석
# 문제라서 py_compile 로는 잡히지 않았다.
def get_search_service(
    db: Session = Depends(get_db),
    chunk_repository: ChunkRepository = Depends(get_chunk_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> SearchService:
    # 임베딩 클라이언트는 lru_cache 로 프로세스당 하나다. 질의 임베딩과 문서
    # 임베딩이 같은 구현체를 써야 같은 벡터 공간이 된다 — 다르면 거리 계산이
    # 에러 없이 무의미해진다.
    # ProjectRepository 는 검색 범위(멤버십)를 확인하는 데 쓴다.
    return SearchService(
        db=db,
        chunk_repository=chunk_repository,
        project_repository=project_repository,
        embedding_client=get_embedding_client(),
    )


def get_auth_service(db: Session = Depends(get_db), users: UserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(db, users)


def get_project_service(db: Session = Depends(get_db), projects: ProjectRepository = Depends(get_project_repository), users: UserRepository = Depends(get_user_repository)) -> ProjectService:
    return ProjectService(db, projects, users)


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), users: UserRepository = Depends(get_user_repository)) -> User:
    user_id = decode_access_token(credentials.credentials) if credentials else None
    user = users.get_by_id(user_id) if user_id else None
    if user is None or not user.is_active:
        raise BusinessError(ErrorCode.UNAUTHORIZED)
    return user


def get_project_access(project_id: int, user: User = Depends(get_current_user), projects: ProjectRepository = Depends(get_project_repository)) -> ProjectAccess:
    row = projects.get_for_user(project_id, user.id)
    if row is None:
        raise BusinessError(ErrorCode.PROJECT_NOT_FOUND)
    return ProjectAccess(*row)


def get_project_editor_access(access: ProjectAccess = Depends(get_project_access)) -> ProjectAccess:
    if access.member.role not in {MemberRole.OWNER.value, MemberRole.EDITOR.value}:
        raise BusinessError(ErrorCode.PROJECT_FORBIDDEN)
    return access


def get_project_owner_access(access: ProjectAccess = Depends(get_project_access)) -> ProjectAccess:
    if access.member.role != MemberRole.OWNER.value or access.project.owner_id != access.member.user_id:
        raise BusinessError(ErrorCode.PROJECT_FORBIDDEN)
    return access


def get_analysis_service(
    db: Session = Depends(get_db),
    document_repository: DocumentRepository = Depends(get_document_repository),
    analysis_repository: AnalysisRepository = Depends(get_analysis_repository),
    analyzer_registry: dict[str, Analyzer] = Depends(get_analyzer_registry),
) -> AnalysisService:
    return AnalysisService(
        db=db,
        document_repository=document_repository,
        analysis_repository=analysis_repository,
        analyzer_registry=analyzer_registry,
    )


def get_extraction_service(
    db: Session = Depends(get_db),
    document_repository: DocumentRepository = Depends(get_document_repository),
    extractor_registry: ExtractorRegistry = Depends(get_extractor_registry),
) -> ExtractionService:
    return ExtractionService(
        db=db,
        document_repository=document_repository,
        extractor_registry=extractor_registry,
    )

def get_document_service(
    db: Session = Depends(get_db),
    document_repository: DocumentRepository = Depends(get_document_repository),
    analysis_repository: AnalysisRepository = Depends(get_analysis_repository),
) -> DocumentService:
    return DocumentService(
        db=db,
        document_repository=document_repository,
        analysis_repository=analysis_repository,
    )

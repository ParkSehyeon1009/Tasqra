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
from app.analyzers.extraction_analyzer import DecisionAnalyzer
from app.analyzers.protocol import Analyzer
from app.analyzers.schedule_analyzer import ScheduleAnalyzer
from app.analyzers.summary_analyzer import SummaryAnalyzer
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.embedding.fake_client import FakeEmbeddingClient
from app.embedding.local_client import LocalEmbeddingClient
from app.embedding.local_model_client import LocalModelEmbeddingClient
from app.embedding.protocol import EmbeddingClientProtocol
from app.rerank.local_model_reranker import LocalModelReranker
from app.rerank.protocol import RerankerProtocol
from app.extractors.docx_extractor import DocxExtractor
from app.extractors.fake_extractor import FakeExtractor
from app.extractors.hwpx_extractor import HwpxExtractor
from app.extractors.image_extractor import ImageExtractor
from app.extractors.ocr_extractor import OcrExtractor
from app.extractors.pdf_extractor import PdfExtractor
from app.extractors.registry import ExtractorRegistry
from app.repositories.amount_repository import AmountRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.deliverable_repository import DeliverableRepository
from app.repositories.decision_schedule_repository import DecisionScheduleRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.repositories.task_repository import TaskRepository
from app.models.enums import MemberRole
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.services.amount_precedent_service import AmountPrecedentService
from app.services.amount_item_service import AmountItemService
from app.services.amount_summary_service import AmountSummaryService
from app.services.amount_task_service import AmountTaskService
from app.services.auth_service import AuthService
from app.services.project_service import ProjectService
from app.services.analysis_service import AnalysisService
from app.services.chunking_service import ChunkingService
from app.services.dashboard_service import DashboardService
from app.services.deliverable_service import DeliverableService
from app.services.decision_schedule_review_service import DecisionScheduleReviewService
from app.services.decision_schedule_writer import DecisionScheduleWriter
from app.services.extraction_service import ExtractionService
from app.services.search_service import SearchService
from app.services.document_service import DocumentService
from app.services.task_service import TaskService

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ProjectAccess:
    project: Project
    member: ProjectMember



@lru_cache
def get_ai_client(model: str | None = None) -> AIClientProtocol:
    """AI 클라이언트를 만든다.

    model 을 주면 그 모델을 부르는 클라이언트가 나온다. 요약과 분류가 서로
    다른 어댑터로 학습되어 별개 모델로 배포되기 때문이다(config.py 주석 참고).
    안 주면 settings.AI_MODEL 을 쓴다.

    ⚠️ lru_cache 가 인자별로 따로 캐싱하므로, 모델 이름마다 클라이언트가 하나씩
      만들어지고 재사용된다.
    """
    # USE_FAKE_AI 기본값은 True — 개발 중 실수로 실제 API가 호출되어 비용이
    # 발생하는 것을 막기 위한 안전장치다. 실제 호출은 .env에서 명시적으로
    # USE_FAKE_AI=false로 바꿔야만 일어난다.
    if settings.USE_FAKE_AI:
        return FakeAIClient()
    # 로컬(Ollama 등 OpenAI 호환) 서버는 호출 비용이 없으므로 USE_FAKE_AI를
    # 끈 뒤 AI_PROVIDER=local로 두고 쓴다. 상용 API 호출은 AI_PROVIDER=openai일
    # 때만 일어난다.
    if settings.AI_PROVIDER.lower() == "local":
        return LocalAIClient(settings, model)
    return OpenAIClient(settings, model)


@lru_cache
def get_embedding_client() -> EmbeddingClientProtocol:
    # USE_FAKE_EMBEDDING 기본값은 True — get_ai_client()의 USE_FAKE_AI와 같은
    # 안전장치인데, 막는 대상이 비용이 아니라 메모리다. 실제 임베딩 모델
    # (BGE-M3 float32)은 약 2.3GB를 잡는다. lru_cache로 프로세스당 한 번만
    # 만드는 것도 그래서다 — uvicorn --reload 환경에서 매번 다시 만들면 못 쓴다.
    if settings.USE_FAKE_EMBEDDING:
        return FakeEmbeddingClient(dimension=settings.EMBEDDING_DIM)
    if settings.EMBEDDING_PROVIDER == "local-http":
        # OpenAI 호환 /v1/embeddings 서버(Ollama 등)를 부른다.
        # 컨테이너 안에 모델을 올리지 않으므로 이미지와 메모리가 늘지 않는다.
        return LocalEmbeddingClient(settings)
    # 기본은 직접 로드다. 서버를 따로 띄우지 않아도 되고, 파인튜닝 어댑터를
    # 저장소에서 바로 읽는다.
    return LocalModelEmbeddingClient(settings)


@lru_cache
def get_reranker() -> RerankerProtocol | None:
    """검색 후보 재정렬기. 꺼져 있으면 None 이다.

    ⚠️ 기본값이 꺼짐인 이유는 비용이다. 후보 10건 재정렬에
    GPU 527ms / CPU 8,511ms 가 걸린다. CPU 에서 켜면 검색이 사실상 멈춘다.
    끄고 limit 을 10 으로 두면 문서 단위 k=10 이 97.2% 로, 리랭커를 켠
    k=5(96.3%)보다 오히려 높다. 리랭커가 사는 것은 정확도가 아니라
    LLM 에 넘길 청크 수다.
    """
    if not settings.RERANK_ENABLED:
        return None
    return LocalModelReranker(settings)


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
    # ⚠️ 분석기마다 다른 모델을 쓴다. 요약과 분류를 서로 다른 LoRA 어댑터로
    #   학습했고, 어댑터 둘을 한 모델로 합칠 수 없기 때문이다.
    #   설정이 비어 있으면 AI_MODEL 로 떨어진다(config.py 주석 참고).
    registry: dict[str, Analyzer] = {
        "summary": SummaryAnalyzer(get_ai_client(settings.AI_MODEL_SUMMARY or None)),
        "category": CategoryAnalyzer(get_ai_client(settings.AI_MODEL_CATEGORY or None)),
        "decision": DecisionAnalyzer(get_ai_client()),
        "schedule": ScheduleAnalyzer(get_ai_client()),
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


def get_task_repository(db: Session = Depends(get_db)) -> TaskRepository:
    return TaskRepository(db)


def get_task_service(
    db: Session = Depends(get_db),
    task_repository: TaskRepository = Depends(get_task_repository),
) -> TaskService:
    return TaskService(db, task_repository)


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
        reranker=get_reranker(),
    )


def get_amount_repository(db: Session = Depends(get_db)) -> AmountRepository:
    return AmountRepository(db)


def get_decision_schedule_repository(
    db: Session = Depends(get_db),
) -> DecisionScheduleRepository:
    return DecisionScheduleRepository(db)


def get_decision_schedule_review_service(
    db: Session = Depends(get_db),
    repository: DecisionScheduleRepository = Depends(get_decision_schedule_repository),
) -> DecisionScheduleReviewService:
    """결정사항·일정 제안 검토 서비스.

    Spring의 @Bean 조립처럼 같은 요청 Session을 Repository와 Service에 주입해
    transactional(db)이 조회한 ORM 행을 그대로 commit하도록 한다.
    """
    return DecisionScheduleReviewService(db, repository)


# get_search_service 와 같은 이유로 get_project_repository · get_amount_repository
# 아래에 두어야 한다. Depends(...) 는 기본값이라 함수를 정의하는 순간 평가된다.
def get_amount_precedent_service(
    db: Session = Depends(get_db),
    amount_repository: AmountRepository = Depends(get_amount_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> AmountPrecedentService:
    # ProjectRepository 는 "내 멤버십 − 현재 프로젝트" 범위를 계산하는 데 쓴다.
    return AmountPrecedentService(db, amount_repository, project_repository)


# get_amount_repository 아래에 두어야 한다 — 위 주석과 같은 이유다.
# Session 을 받지 않는다. 이 서비스는 리포지토리를 통해서만 DB 를 만지고,
# 트랜잭션을 열 일이 없는 순수 조회다.
def get_amount_summary_service(
    amount_repository: AmountRepository = Depends(get_amount_repository),
    task_repository: TaskRepository = Depends(get_task_repository),
) -> AmountSummaryService:
    return AmountSummaryService(amount_repository, task_repository)


def get_amount_item_service(
    db: Session = Depends(get_db),
    amount_repository: AmountRepository = Depends(get_amount_repository),
    task_repository: TaskRepository = Depends(get_task_repository),
    task_service: TaskService = Depends(get_task_service),
) -> AmountItemService:
    """금액 항목을 고치는 서비스 (AMT-001-2).

    태스크가 둘 필요하다.
      · `TaskRepository` — 응답에 `task_id` 를 붙인다(목록과 같은 모양이어야 화면이
        그 줄만 갈아끼울 수 있다)
      · `TaskService` — 고친 결과를 연결된 태스크 설명의 «자동 기록» 에 적는다
    """
    return AmountItemService(db, amount_repository, task_repository, task_service)


def get_amount_task_service(
    amount_repository: AmountRepository = Depends(get_amount_repository),
    task_repository: TaskRepository = Depends(get_task_repository),
    task_service: TaskService = Depends(get_task_service),
) -> AmountTaskService:
    """금액 불일치를 태스크로 만드는 서비스 (AMT-004-3).

    태스크를 만드는 것은 TaskService 에 맡긴다 — 제목 검증·담당자 확인·활동 기록이
    거기 있고, 그것을 복사하면 제안으로 만든 태스크만 활동 로그에 안 남는다.
    """
    return AmountTaskService(amount_repository, task_repository, task_service)


def get_dashboard_repository(db: Session = Depends(get_db)) -> DashboardRepository:
    return DashboardRepository(db)


# get_search_service 와 같은 이유로 get_dashboard_repository **아래에** 두어야
# 한다. Depends(...) 는 기본값이라 함수를 정의하는 순간 평가된다.
def get_dashboard_service(
    dashboard_repository: DashboardRepository = Depends(get_dashboard_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> DashboardService:
    # 프로젝트 단건 현황은 기존처럼 전달받은 project_id만 읽는다. 전역 포트폴리오
    # 현황은 ProjectRepository로 현재 사용자의 멤버십 범위를 한 번 계산한 뒤,
    # DashboardRepository의 bulk 조회로 모은다.
    return DashboardService(dashboard_repository, project_repository)


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


# 금액 열람 권한. **정책이 아직 미결이라 여기 한 곳에 모아 둔다** (AMT-003-1).
#
# 지금은 VIEWER 를 막는다. 역할별 허용 표에서 금액 항목 조회의 VIEWER 칸이
# "미결" 로 남아 있고, 멤버 역할 변경(PRJ-004-3)에도 "금액 열람 권한은 함께 정책
# 확정 필요" 가 붙어 있다.
#
# 왜 막는 쪽을 기본값으로 두는가 — 방향이 비대칭이다
#   막았다가 푸는 것은 이 함수 한 줄이다. 열었다가 막는 것은 **이미 본 뒤**라
#   되돌릴 수 없다. 금액은 계약 정보라 특히 그렇다.
#
# ⚠️ 단가 선례 조회(amount-precedents)는 get_project_access 를 써서 VIEWER 에게
#   열려 있다. 정책이 정해지면 **그것도 이 함수로 옮겨** 두 엔드포인트가 갈리지
#   않게 해야 한다. 지금 옮기지 않은 이유는 이미 동작하는 기능의 권한을 바꾸는
#   일이라 팀 합의가 필요해서다.
#
# get_project_editor_access 를 그대로 쓰지 않는 이유: 지금은 판정이 같지만 뜻이
#   다르다. 그것은 "고칠 수 있는가" 이고 이것은 "금액을 볼 수 있는가" 다. 정책이
#   정해져 VIEWER 에게 열면 둘이 갈라지는데, 같은 함수를 쓰고 있으면 그때 금액을
#   열면서 편집 권한까지 함께 열게 된다.
def get_project_amount_access(access: ProjectAccess = Depends(get_project_access)) -> ProjectAccess:
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
    decision_schedule_repository: DecisionScheduleRepository = Depends(
        get_decision_schedule_repository
    ),
    analyzer_registry: dict[str, Analyzer] = Depends(get_analyzer_registry),
) -> AnalysisService:
    decision_schedule_writer = DecisionScheduleWriter(
        analysis_repository,
        decision_schedule_repository,
    )
    return AnalysisService(
        db=db,
        document_repository=document_repository,
        analysis_repository=analysis_repository,
        analyzer_registry=analyzer_registry,
        decision_schedule_writer=decision_schedule_writer,
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
        ocr_extractor=get_ocr_extractor(),
    )



# --- 산출물 (DLV-001-2 생성 대상 미리보기) ----------------------------------


def get_deliverable_repository(db: Session = Depends(get_db)) -> DeliverableRepository:
    return DeliverableRepository(db)


# get_search_service · get_dashboard_service 와 같은 이유로
# get_deliverable_repository **아래에** 두어야 한다. Depends(...) 는 기본값이라
# 함수를 정의하는 순간 평가되고, 위에 두면 import 시점에 NameError 로 앱이 안 뜬다.
def get_deliverable_service(
    db: Session = Depends(get_db),
    deliverable_repository: DeliverableRepository = Depends(get_deliverable_repository),
) -> DeliverableService:
    # 세션을 넘기는 이유는 **만들기(DLV-002-x)** 다. 파일 저장과 이력 저장을 한
    # 트랜잭션으로 묶어야 해서 서비스가 transactional 을 쓴다. 미리보기는 여전히
    # 읽기만 하고 조회는 전부 리포지토리를 거친다.
    # ProjectRepository 는 넘기지 않는다 — 범위가 현재 프로젝트 하나로 정해져 있고
    # 권한은 라우터의 get_project_access 가 이미 판정했다.
    #
    # ai_client 는 개요(DLV-002-1·DLV-002-2)를 1회 호출로 만들 때 쓴다. analyzer
    # 레지스트리와 같은 get_ai_client() 를 공유하므로 USE_FAKE_AI·AI_PROVIDER
    # 설정이 산출물 개요에도 그대로 적용된다.
    return DeliverableService(deliverable_repository, db, get_ai_client())


def get_analysis_job_service(
    db: Session = Depends(get_db),
    documents: DocumentRepository = Depends(get_document_repository),
    analysis: AnalysisService = Depends(get_analysis_service),
):
    from app.repositories.analysis_job_repository import AnalysisJobRepository
    from app.services.analysis_job_service import AnalysisJobService
    return AnalysisJobService(db, documents, AnalysisJobRepository(db), analysis)

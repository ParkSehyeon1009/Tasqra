# =============================================================================
# 이 파일의 책임: 단일 프로젝트 문서 기반 질의응답 챗봇(CHAT-001)의 HTTP 경계를
#   정의한다. 질문 한 건을 받고 답변과 실제 근거 목록을 반환한다.
# 다른 파일과의 관계: get_project_access가 멤버 권한을 먼저 확인하고,
#   ChatService가 기존 project_ids 검색 정책·컨텍스트 조립·LLM 호출을 수행한다.
# Spring 비교: @RestController + 프로젝트 접근 HandlerInterceptor에 해당한다.
# =============================================================================

from fastapi import APIRouter, Depends

from app.dependencies import ProjectAccess, get_chat_service, get_project_access
from app.schemas.chat import ChatQuestionRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def ask_project_documents(
    project_id: int,
    request: ChatQuestionRequest,
    access: ProjectAccess = Depends(get_project_access),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """현재 프로젝트 문서만 검색해 근거 기반 답변을 만든다."""
    return await service.ask(
        user_id=access.member.user_id,
        project_id=project_id,
        question=request.question,
    )

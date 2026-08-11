from fastapi import APIRouter, Depends

from app.dependencies import ProjectAccess, get_analysis_service, get_project_editor_access
from app.schemas.document import AnalyzeRequest, AnalyzeResponse, AnalysisResponse
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["analysis"])

@router.post("/documents/{document_id}/analyze", response_model=AnalyzeResponse)
async def analyze_document(document_id: int, request: AnalyzeRequest, access: ProjectAccess = Depends(get_project_editor_access), service: AnalysisService = Depends(get_analysis_service)):
    analyses = await service.analyze_document(access.project.id, document_id, request.analyzer_types)
    return AnalyzeResponse(document_id=document_id, analyses=[AnalysisResponse.model_validate(item) for item in analyses])

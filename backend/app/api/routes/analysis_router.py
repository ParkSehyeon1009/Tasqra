from fastapi import APIRouter, Depends

from app.dependencies import get_analysis_service
from app.schemas.document import AnalyzeRequest, AnalyzeResponse, AnalysisResponse
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/documents/{document_id}/analyze", response_model=AnalyzeResponse)
async def analyze_document(
    document_id: int,
    request: AnalyzeRequest,
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalyzeResponse:
    analyses = await service.analyze_document(document_id, request.analyzer_types)
    return AnalyzeResponse(
        document_id=document_id,
        analyses=[AnalysisResponse.model_validate(analysis) for analysis in analyses],
    )

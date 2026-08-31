from fastapi import APIRouter, Depends

from app.core.middleware import get_request_id
from app.dependencies import ProjectAccess, get_analysis_job_service, get_project_access, get_project_editor_access
from app.schemas.document import AnalyzeRequest, AnalysisJobResponse
from app.services.analysis_job_service import AnalysisJobService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["analysis"])


@router.post("/documents/{document_id}/analyze", response_model=AnalysisJobResponse, status_code=202)
def analyze_document(document_id: int, request: AnalyzeRequest,
    access: ProjectAccess = Depends(get_project_editor_access),
    service: AnalysisJobService = Depends(get_analysis_job_service),
    request_id: str = Depends(get_request_id)):
    from app.worker import analyze_document_task
    return service.enqueue(access.project.id, document_id, request.analyzer_types,
        lambda project, document, job: analyze_document_task.delay(project, document, job, request_id=request_id))


@router.get("/documents/{document_id}/analysis-jobs/latest", response_model=AnalysisJobResponse | None)
def latest_analysis(document_id: int, access: ProjectAccess = Depends(get_project_access),
    service: AnalysisJobService = Depends(get_analysis_job_service)):
    return service.get(access.project.id, document_id)


@router.get("/documents/{document_id}/analysis-jobs/{job_id}", response_model=AnalysisJobResponse)
def get_analysis_job(document_id: int, job_id: str, access: ProjectAccess = Depends(get_project_access),
    service: AnalysisJobService = Depends(get_analysis_job_service)):
    return service.get(access.project.id, document_id, job_id)

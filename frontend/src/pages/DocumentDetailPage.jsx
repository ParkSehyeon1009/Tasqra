// =============================================================================
// 이 파일의 책임: 문서 상세 정보와 내용·OCR 검수·분석·변경 이력 탭을 보여준다.
// 다른 파일과의 관계: 문서 목록이 router state로 넘긴 복귀 URL을 상세와 OCR 검수
//   화면까지 유지해, 사용자가 기존 유형 필터가 적용된 목록으로 돌아가게 한다.
// Spring 비교: 문서 상세 Controller와 탭별 View를 조합한 화면이며, 목록 복귀 URL은
//   RedirectAttributes처럼 다음 화면 이동에만 쓰는 탐색 상태다.
// =============================================================================

import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { startDocumentAnalysis, getAnalysisJob, deleteDocument, downloadDocumentSource, downloadSummary, getDocument, retryDocumentProcessing } from '../api/document'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import ConfirmDialog from '../components/common/ConfirmDialog'
import LoadingState from '../components/common/LoadingState'
import DocumentAnalysisTab from '../features/document-detail/DocumentAnalysisTab'
import DocumentContentTab from '../features/document-detail/DocumentContentTab'
import DocumentHeader from '../features/document-detail/DocumentHeader'
import DocumentHistoryTab from '../features/document-detail/DocumentHistoryTab'
import DocumentReviewTab from '../features/document-detail/DocumentReviewTab'
import DecisionScheduleReviewPanel from '../features/decision-schedule/DecisionScheduleReviewView'
import ProjectSidebar from '../features/projects/ProjectSidebar'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import '../styles/document-detail-page.css'
import '../styles/document-detail-updates.css'

const TABS = [['content', '문서 내용'], ['review', 'OCR 검수'], ['analysis', '분석 결과'], ['history', '변경 이력']]

function getDocumentListUrl(projectId, candidate) {
  const fallback = `/projects/${projectId}/documents`
  return candidate === fallback || candidate?.startsWith(`${fallback}?`) ? candidate : fallback
}

export default function DocumentDetailPage({ user, onLogout, notify }) {
  const { projectId, documentId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const documentListUrl = getDocumentListUrl(projectId, location.state?.documentListUrl)
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const { projects } = useProjectsQuery(notify)
  const activeTab = TABS.some(([key]) => key === params.get('tab')) ? params.get('tab') : 'content'
  const projectQuery = useQuery({ queryKey: ['project-access', projectId], queryFn: () => getProject(projectId), retry: false })
  const documentKey = ['projects', projectId, 'documents', documentId]
  const documentQuery = useQuery({ queryKey: documentKey, queryFn: () => getDocument(projectId, documentId), retry: false, refetchInterval: query => ['PENDING', 'EXTRACTING'].includes(query.state.data?.status) ? 3_000 : false })
  const document = documentQuery.data
  const canEdit = projectQuery.data?.role !== 'VIEWER'
  const jobKey = ['analysis-jobs', projectId, documentId]
  const jobQuery = useQuery({ queryKey: jobKey, queryFn: () => getAnalysisJob(projectId, documentId), retry: false,
    refetchInterval: query => ['PENDING', 'RUNNING'].includes(query.state.data?.status) ? 2000 : false })
  const job = jobQuery.data
  const analysisRunning = ['PENDING', 'RUNNING'].includes(job?.status)
  const previousJob = useRef(null)
  const completedJob = useRef(null)
  useEffect(() => {
    if (job?.status === 'COMPLETED' && completedJob.current !== job.job_id) {
      completedJob.current = job.job_id
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId] })
      queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] })
      queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'dashboard'] })
      if (previousJob.current === job.job_id) notify('success', '문서 분석 완료', '분석 결과를 생성했습니다.')
    }
    previousJob.current = ['PENDING', 'RUNNING'].includes(job?.status) ? job.job_id : null
  }, [job?.status, job?.job_id, projectId, documentId, queryClient, notify])
  const analyzeMutation = useMutation({ mutationFn: () => startDocumentAnalysis(projectId, documentId),
    onSuccess: data => { queryClient.setQueryData(jobKey, data); notify('success', '문서 분석 접수', '화면을 닫아도 분석은 계속됩니다.') },
    onError: error => notify('error', '문서 분석 실패', error.message) })
  const deleteMutation = useMutation({ mutationFn: () => deleteDocument(projectId, documentId), onSuccess: () => { queryClient.removeQueries({ queryKey: documentKey }); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] }); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'dashboard'] }); notify('success', '문서 삭제 완료', `${document.filename} 문서를 삭제했습니다.`); navigate(documentListUrl, { replace: true }) }, onError: error => notify('error', '문서 삭제 실패', error.message) })
  const downloadMutation = useMutation({ mutationFn: () => downloadDocumentSource(projectId, documentId, document.filename), onError: error => notify('error', '원본 다운로드 실패', error.message) })
  const summaryDownloadMutation = useMutation({ mutationFn: () => downloadSummary(projectId, documentId, `${document.filename.replace(/\.[^.]+$/, '')}_요약.txt`), onSuccess: () => notify('success', '분석 결과 다운로드 완료', '최신 요약과 분류 결과를 저장했습니다.'), onError: error => notify('error', '분석 결과 다운로드 실패', error.message) })
  const retryMutation = useMutation({ mutationFn: () => retryDocumentProcessing(projectId, documentId), onSuccess: () => { queryClient.setQueryData(documentKey, current => ({ ...current, status: 'PENDING', processing_error: null })); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] }); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'dashboard'] }); notify('success', '문서 재처리 접수', `${document.filename} 처리를 다시 시작했습니다.`) }, onError: error => notify('error', '문서 재처리 실패', error.message) })

  if (projectQuery.isPending || documentQuery.isPending) return <LoadingState label="문서 상세 화면을 불러오는 중..."/>
  if (projectQuery.isError) return <div className="detail-not-found"><h1>프로젝트에 접근할 수 없습니다.</h1><p>프로젝트가 없거나 접근 권한이 없습니다.</p><button onClick={() => navigate('/projects')}>내 프로젝트로 이동</button></div>
  if (documentQuery.isError || !document) return <div className="detail-not-found"><h1>문서를 열 수 없습니다.</h1><p>문서가 없거나 삭제되었을 수 있습니다.</p><button onClick={() => navigate(documentListUrl)}>문서 목록으로 돌아가기</button></div>
  return <div className="app-frame document-detail-page">
    <AppHeader user={user} onLogout={onLogout} notify={notify} project={projectQuery.data} section="문서 상세"/>
    <ProjectSidebar projects={projects} activeProjectId={projectId} activeTab="documents" onSelect={selected => navigate(`/projects/${selected.id}/dashboard`)} onNavigateTab={key => navigate(`/projects/${projectId}/${key}`)} onCreate={() => navigate('/projects')}/>
    <div className="standalone-workspace-content"><div className="document-detail-shell">
      <DocumentHeader document={document} canEdit={canEdit} busy={deleteMutation.isPending || downloadMutation.isPending || retryMutation.isPending} onBack={() => navigate(documentListUrl)} onDownload={() => downloadMutation.mutate()} onRetry={() => retryMutation.mutate()} onDelete={() => setDeleteOpen(true)}/>
      <nav className="document-detail-tabs">{TABS.map(([key, label]) => <button className={activeTab === key ? 'active' : ''} key={key} onClick={() => setParams({ tab: key }, { state: { documentListUrl } })}>{label}</button>)}</nav>
      <main className="document-tab-body">
        {analysisRunning && <section className="detail-card" role="status"><strong>AI 분석: {job.stage}</strong>{job.total_units > 0 && <p>현재 단계 {job.completed_units}/{job.total_units}</p>}<p>화면을 닫아도 분석은 계속됩니다.</p></section>}
        {job?.status === 'FAILED' && <section className="detail-card" role="alert"><strong>AI 분석 실패: {job.stage}</strong><p>{job.error_message}</p></section>}
        {jobQuery.error && <p role="alert">분석 상태 조회 실패: {jobQuery.error.message}</p>}
        {activeTab === 'content' && <DocumentContentTab document={document}/>}
        {activeTab === 'review' && <DocumentReviewTab document={document} onOpenReview={() => navigate(`/projects/${projectId}/documents/${documentId}/review`, { state: { documentListUrl } })}/>}
        {activeTab === 'analysis' && <div className="document-analysis-layout">
          <DocumentAnalysisTab document={document} canAnalyze={canEdit} analyzing={analyzeMutation.isPending || analysisRunning} onAnalyze={() => analyzeMutation.mutate()} downloading={summaryDownloadMutation.isPending} onDownload={() => summaryDownloadMutation.mutate()}/>
          <DecisionScheduleReviewPanel projectId={projectId} documentId={documentId} canEdit={canEdit} notify={notify}/>
        </div>}
        {activeTab === 'history' && <DocumentHistoryTab projectId={projectId} document={document}/>}
      </main>
    </div></div>
    <ConfirmDialog open={deleteOpen} title="문서를 완전히 삭제하시겠습니까?" message="원본 파일, 추출 텍스트, OCR 수정 이력과 분석 결과가 모두 삭제되며 복구할 수 없습니다." confirmationText={document.filename} confirmLabel="문서 영구 삭제" danger onCancel={() => setDeleteOpen(false)} onConfirm={() => { setDeleteOpen(false); deleteMutation.mutate() }}/>
  </div>
}

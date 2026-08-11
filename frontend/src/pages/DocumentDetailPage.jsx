import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { analyzeDocument, deleteDocument, downloadDocumentSource, downloadSummary, getDocument } from '../api/document'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import ConfirmDialog from '../components/common/ConfirmDialog'
import LoadingState from '../components/common/LoadingState'
import DocumentAnalysisTab from '../features/document-detail/DocumentAnalysisTab'
import DocumentContentTab from '../features/document-detail/DocumentContentTab'
import DocumentHeader from '../features/document-detail/DocumentHeader'
import DocumentHistoryTab from '../features/document-detail/DocumentHistoryTab'
import DocumentReviewTab from '../features/document-detail/DocumentReviewTab'
import '../styles/document-detail-page.css'
import '../styles/document-detail-updates.css'

const TABS = [['content', '문서 내용'], ['review', 'OCR 검수'], ['analysis', '분석 결과'], ['history', '변경 이력']]

export default function DocumentDetailPage({ user, onLogout, notify }) {
  const { projectId, documentId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [deleteOpen, setDeleteOpen] = useState(false)
  const activeTab = TABS.some(([key]) => key === params.get('tab')) ? params.get('tab') : 'content'
  const projectQuery = useQuery({ queryKey: ['project-access', projectId], queryFn: () => getProject(projectId), retry: false })
  const documentKey = ['projects', projectId, 'documents', documentId]
  const documentQuery = useQuery({ queryKey: documentKey, queryFn: () => getDocument(projectId, documentId), retry: false })
  const document = documentQuery.data
  const canEdit = projectQuery.data?.role !== 'VIEWER'
  const analyzeMutation = useMutation({ mutationFn: () => analyzeDocument(projectId, documentId), onSuccess: () => { queryClient.invalidateQueries({ queryKey: documentKey }); notify('success', '문서 분석 완료', '현재 텍스트를 기준으로 분석 결과를 생성했습니다.') }, onError: error => notify('error', '문서 분석 실패', error.message) })
  const deleteMutation = useMutation({ mutationFn: () => deleteDocument(projectId, documentId), onSuccess: () => { queryClient.removeQueries({ queryKey: documentKey }); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] }); notify('success', '문서 삭제 완료', `${document.filename} 문서를 삭제했습니다.`); navigate(`/projects/${projectId}/documents`, { replace: true }) }, onError: error => notify('error', '문서 삭제 실패', error.message) })
  const downloadMutation = useMutation({ mutationFn: () => downloadDocumentSource(projectId, documentId, document.filename), onError: error => notify('error', '원본 다운로드 실패', error.message) })
  const summaryDownloadMutation = useMutation({ mutationFn: () => downloadSummary(projectId, documentId, `${document.filename.replace(/\.[^.]+$/, '')}_요약.txt`), onSuccess: () => notify('success', '분석 결과 다운로드 완료', '최신 요약과 분류 결과를 저장했습니다.'), onError: error => notify('error', '분석 결과 다운로드 실패', error.message) })

  if (projectQuery.isPending || documentQuery.isPending) return <LoadingState label="문서 상세 화면을 불러오는 중..."/>
  if (projectQuery.isError || documentQuery.isError || !document) return <div className="detail-not-found"><h1>문서를 열 수 없습니다.</h1><p>문서가 없거나 프로젝트 접근 권한이 없습니다.</p><button onClick={() => navigate('/projects')}>내 프로젝트로 이동</button></div>
  return <div className="document-detail-page">
    <AppHeader user={user} onLogout={onLogout} notify={notify} project={projectQuery.data}/>
    <div className="document-detail-shell">
      <DocumentHeader document={document} canEdit={canEdit} busy={deleteMutation.isPending || downloadMutation.isPending} onBack={() => navigate(`/projects/${projectId}/documents`)} onDownload={() => downloadMutation.mutate()} onDelete={() => setDeleteOpen(true)}/>
      <nav className="document-detail-tabs">{TABS.map(([key, label]) => <button className={activeTab === key ? 'active' : ''} key={key} onClick={() => setParams({ tab: key })}>{label}{key === 'analysis' && document.analyses.length > 0 && <b>{document.analyses.length}</b>}</button>)}</nav>
      <main className="document-tab-body">
        {activeTab === 'content' && <DocumentContentTab document={document}/>}
        {activeTab === 'review' && <DocumentReviewTab document={document} onOpenReview={() => navigate(`/projects/${projectId}/documents/${documentId}/review`)}/>}
        {activeTab === 'analysis' && <DocumentAnalysisTab document={document} canAnalyze={canEdit} analyzing={analyzeMutation.isPending} onAnalyze={() => analyzeMutation.mutate()} downloading={summaryDownloadMutation.isPending} onDownload={() => summaryDownloadMutation.mutate()}/>}
        {activeTab === 'history' && <DocumentHistoryTab projectId={projectId} document={document}/>}
      </main>
    </div>
    <ConfirmDialog open={deleteOpen} title="문서를 완전히 삭제하시겠습니까?" message="원본 파일, 추출 텍스트, OCR 수정 이력과 분석 결과가 모두 삭제되며 복구할 수 없습니다." confirmationText={document.filename} confirmLabel="문서 영구 삭제" danger onCancel={() => setDeleteOpen(false)} onConfirm={() => { setDeleteOpen(false); deleteMutation.mutate() }}/>
  </div>
}

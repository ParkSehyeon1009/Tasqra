// =============================================================================
// 이 파일의 책임: 프로젝트 탭 URL과 공통 워크스페이스 데이터를 연결하고 각 기능
//   화면에 필요한 props를 전달한다.
// 다른 파일과의 관계: document_type query를 useWorkspaceData와 DocumentsView에
//   전달하며 DashboardView·BoardView 등 탭 화면의 조립점이다.
// Spring 비교: 라우팅과 화면 조립을 담당하는 MVC Controller에 가깝다.
// =============================================================================

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import BoardView from '../features/board/BoardView'
import AmountSummaryView from '../features/amount/AmountSummaryView'
import DashboardView from '../features/dashboard/DashboardView'
import DeliverablesView from '../features/deliverables/DeliverablesView'
import DocumentsView from '../features/documents/DocumentsView'
import DocumentUploadModal from '../features/documents/DocumentUploadModal'
import MembersView from '../features/members/MembersView'
import ProjectCreateModal from '../features/projects/ProjectCreateModal'
import ProjectSidebar from '../features/projects/ProjectSidebar'
import SearchView from '../features/search/SearchView'
import { isImageUpload } from '../features/document-upload/uploadValidation'
import { useInvitationsQuery } from '../hooks/useInvitationsQuery'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import { useWorkspaceData } from '../hooks/useWorkspaceData'
import { normalizeDocumentTypeFilter } from '../utils/documentType'
import { clearRecentProjectId, setRecentProjectId } from '../utils/recentProject'
import '../styles/workspace.css'

// 탭을 추가할 때는 이 배열과 아래 TabContent 를 **함께** 고쳐야 한다.
// TabContent 마지막이 return <BoardView/> 로 떨어지므로, 여기만 추가하면
// 새 탭에서 보드가 나온다 — 에러가 나지 않아 찾기 어렵다.
//
// **세 번째 자리가 하나 더 있다** — features/projects/ProjectSidebar.jsx 의
// PROJECT_MENUS 다. 거기가 사이드바에서 눌러 들어가는 목록이고, 이 배열은
// 주소로 들어왔을 때 허용하는 목록이다(없으면 대시보드로 되돌린다).
// 셋 중 하나를 빠뜨리면 에러 없이 어긋난다.
const TABS = [['dashboard','대시보드'],['documents','문서'],['search','검색'],['amounts','금액'],['deliverables','산출물'],['board','보드'],['settings','설정']]

export default function WorkspacePage({ user, onLogout, notify }) {
  const { projectId, tab } = useParams()
  const navigate = useNavigate()
  const projectQuery = useQuery({
    queryKey: ['project-access', projectId],
    queryFn: () => getProject(projectId),
    retry: false,
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
    refetchInterval: 3_000,
  })
  const { projects, createMutation, deleteMutation } = useProjectsQuery(notify)
  const { recentInvitees } = useInvitationsQuery(user?.id, notify)
  const project = projectQuery.data
  if (!TABS.some(([key]) => key === tab)) return <Navigate to={`/projects/${projectId}/dashboard`} replace/>
  if (projectQuery.isPending) return <LoadingState label="프로젝트 접근 권한을 확인하는 중..."/>
  if (projectQuery.isError || !project) return <Navigate to="/projects" replace/>
  return <WorkspaceContent project={project} projects={projects} tab={tab} navigate={navigate} notify={notify} user={user} onLogout={onLogout} createMutation={createMutation} deleteMutation={deleteMutation} recentInvitees={recentInvitees}/>
}

function WorkspaceContent({ project, projects, tab, navigate, notify, user, onLogout, createMutation, deleteMutation, recentInvitees }) {
  const [creating, setCreating] = useState(false)
  const [uploadFiles, setUploadFiles] = useState([])
  const [uploadQueue, setUploadQueue] = useState([])
  const [searchParams, setSearchParams] = useSearchParams()
  const documentType = normalizeDocumentTypeFilter(searchParams.get('document_type'))
  // 문서 탭에서만 query를 목록 조회에 적용한다. 다른 탭의 URL에 같은 query가
  // 붙어도 대시보드 OCR 미리보기까지 유형별로 좁아지면 안 된다.
  const activeDocumentType = tab === 'documents' ? documentType : ''
  const data = useWorkspaceData(project, notify, { documentType: activeDocumentType })
  const fileInputRef = useRef(null)
  const uploadSequenceRef = useRef(Promise.resolve())
  const scheduledUploadIdsRef = useRef(new Set())
  const nextUploadIdRef = useRef(1)
  const canEdit = project.role !== 'VIEWER'
  const openUpload = () => fileInputRef.current?.click()

  useEffect(() => { setRecentProjectId(user?.id, project.id) }, [project.id, user?.id])

  async function createNewProject(values) {
    try {
      const { project: created } = await createMutation.mutateAsync(values)
      setCreating(false)
      setRecentProjectId(user?.id, created.id)
      navigate(`/projects/${created.id}/dashboard`)
    } catch { /* 공통 토스트에서 처리 */ }
  }
  function requestUpload(selectedFiles) {
    if (!selectedFiles || !canEdit) return
    const files = selectedFiles instanceof File ? [selectedFiles] : Array.from(selectedFiles)
    if (files.length) setUploadFiles(files)
  }
  function confirmUpload(files, extractionStrategy, documentType) {
    const queuedItems = files.map(file => ({
      id: nextUploadIdRef.current++,
      projectId: project.id,
      file,
      extractionStrategy,
      documentType,
      status: 'QUEUED',
      error: null,
    }))
    setUploadFiles([])
    setUploadQueue(current => [...current, ...queuedItems])
    queuedItems.forEach(scheduleUpload)
  }

  function scheduleUpload(item) {
    if (scheduledUploadIdsRef.current.has(item.id)) return
    scheduledUploadIdsRef.current.add(item.id)
    setUploadQueue(current => current.map(queued => queued.id === item.id ? { ...queued, status: 'QUEUED', error: null } : queued))
    uploadSequenceRef.current = uploadSequenceRef.current.then(async () => {
      setUploadQueue(current => current.map(queued => queued.id === item.id ? { ...queued, status: 'UPLOADING' } : queued))
      try {
        await data.uploadFile(item.file, isImageUpload(item.file) ? 'AUTO' : item.extractionStrategy, item.documentType)
        setUploadQueue(current => current.map(queued => queued.id === item.id ? { ...queued, status: 'COMPLETED' } : queued))
      } catch (error) {
        setUploadQueue(current => current.map(queued => queued.id === item.id ? { ...queued, status: 'FAILED', error: error.message || '업로드에 실패했습니다.' } : queued))
      } finally {
        scheduledUploadIdsRef.current.delete(item.id)
      }
    })
  }
  async function upload(event) {
    const files = event.target.files
    if (!files?.length) return
    try { await requestUpload(files) } catch { /* 공통 토스트에서 처리 */ }
    finally { event.target.value = '' }
  }
  async function deleteCurrentProject() {
    try {
      await deleteMutation.mutateAsync(project.id)
      clearRecentProjectId(user?.id, project.id)
      navigate('/projects', { replace: true })
    } catch { /* 공통 토스트에서 처리 */ }
  }
  function changeDocumentType(documentType) {
    const nextSearchParams = new URLSearchParams(searchParams)
    if (documentType) nextSearchParams.set('document_type', documentType)
    else nextSearchParams.delete('document_type')
    setSearchParams(nextSearchParams)
  }

  return <div className="app-frame"><AppHeader user={user} onLogout={onLogout} notify={notify} project={project} section={TABS.find(([key]) => key === tab)?.[1]}/><input ref={fileInputRef} hidden type="file" multiple accept=".pdf,.docx,.hwpx,.png,.jpg,.jpeg" onChange={upload}/>
    <div className="workspace-shell">
      <ProjectSidebar projects={projects} activeProjectId={project.id} activeTab={tab} onSelect={selected => navigate(`/projects/${selected.id}/dashboard`)} onNavigateTab={key => navigate(`/projects/${project.id}/${key}`)} onCreate={() => setCreating(true)}/>
      <section className="workspace-content">
        <main className="workspace-main">{data.loading ? <LoadingState label="프로젝트 데이터를 불러오는 중..."/> : <TabContent tab={tab} project={project} data={data} documentType={documentType} onDocumentTypeChange={changeDocumentType} canEdit={canEdit} notify={notify} onUpload={openUpload} onFileDrop={requestUpload} uploadQueue={uploadQueue.filter(item => item.projectId === project.id)} onRetryUpload={scheduleUpload} onClearUploadQueue={() => setUploadQueue(current => current.filter(item => item.projectId !== project.id || ['QUEUED', 'UPLOADING'].includes(item.status)))} onDeleteProject={deleteCurrentProject} deleting={deleteMutation.isPending}/>}</main>
      </section>
    </div>
    <ProjectCreateModal open={creating} recentInvitees={recentInvitees} pending={createMutation.isPending} onClose={() => setCreating(false)} onSubmit={createNewProject}/>
    {uploadFiles.length > 0 && <DocumentUploadModal files={uploadFiles} uploading={false} onClose={() => setUploadFiles([])} onRemove={index => setUploadFiles(current => current.filter((_, currentIndex) => currentIndex !== index))} onSubmit={confirmUpload}/>}
  </div>
}

function TabContent({ tab, project, data, documentType, onDocumentTypeChange, canEdit, notify, onUpload, onFileDrop, uploadQueue, onRetryUpload, onClearUploadQueue, onDeleteProject, deleting }) {
  if (tab === 'documents') return <DocumentsView projectId={project.id} documents={data.documents} documentsTotal={data.documentsTotal} documentType={documentType} onDocumentTypeChange={onDocumentTypeChange} canEdit={canEdit} onUpload={onUpload} onFileDrop={onFileDrop} uploadQueue={uploadQueue} onRetryUpload={onRetryUpload} onClearUploadQueue={onClearUploadQueue} onRetry={data.retryDocument} retryingDocumentId={data.retryingDocumentId}/>
  if (tab === 'settings') return <MembersView project={project} members={data.members} invitations={data.invitations} onUpdateProject={data.updateProject} updatingProject={data.updatingProject} onInvite={data.invite} onCancelInvitation={data.cancelInvitation} onRole={data.changeRole} onRemove={data.excludeMember} onDeleteProject={onDeleteProject} deleting={deleting}/>
  if (tab === 'dashboard') return <DashboardView projectId={project.id} documents={data.documents} members={data.members}/>
  // 검색은 워크스페이스 데이터(문서 목록 · 멤버)를 쓰지 않는다. 자기 상태만
  // 들고 api/search.js 를 부른다. 범위 토글에 쓸 프로젝트 이름만 넘긴다.
  if (tab === 'search') return <SearchView projectId={project.id} projectName={project.name}/>
  // 산출물도 워크스페이스 데이터를 쓰지 않는다. 건수는 서버가 세므로(DLV-001-2)
  // 화면에 넘겨준 문서 목록으로 다시 세지 않는다 — 그 목록은 첫 페이지라
  // 문서가 21건 이상이면 조용히 틀린다(대시보드에서 겪은 것과 같은 함정).
  // notify 는 만들기가 아직 준비 중임을 알리는 데 쓴다.
  if (tab === 'deliverables') return <DeliverablesView projectId={project.id} notify={notify}/>
  // 금액도 워크스페이스 데이터를 쓰지 않는다. 합계는 서버가 내므로(AMT-002-2)
  // 화면에 넘어온 문서 목록으로 다시 세거나 더하지 않는다.
  if (tab === 'amounts') return <AmountSummaryView projectId={project.id} notify={notify}/>
  return <BoardView projectId={project.id} members={data.members} canEdit={canEdit} notify={notify}/>
}

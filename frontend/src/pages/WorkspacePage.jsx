import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import BoardView from '../features/board/BoardView'
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
import { clearRecentProjectId, setRecentProjectId } from '../utils/recentProject'
import '../styles/workspace.css'

// 탭을 추가할 때는 이 배열과 아래 TabContent 를 **함께** 고쳐야 한다.
// TabContent 마지막이 return <BoardView/> 로 떨어지므로, 여기만 추가하면
// 새 탭에서 보드가 나온다 — 에러가 나지 않아 찾기 어렵다.
const TABS = [['dashboard','대시보드'],['documents','문서'],['search','검색'],['deliverables','산출물'],['board','보드'],['settings','설정']]

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
  const data = useWorkspaceData(project, notify)
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

  return <div className="app-frame"><AppHeader user={user} onLogout={onLogout} notify={notify} project={project}/><input ref={fileInputRef} hidden type="file" multiple accept=".pdf,.docx,.hwpx,.png,.jpg,.jpeg" onChange={upload}/>
    <div className="workspace-shell">
      <ProjectSidebar projects={projects} activeProjectId={project.id} onSelect={selected => navigate(`/projects/${selected.id}/dashboard`)} onCreate={() => setCreating(true)}/>
      <section className="workspace-content">
        <nav className="tabs" aria-label="프로젝트 메뉴">{TABS.map(([key,label]) => <button className={tab === key ? 'active' : ''} onClick={() => navigate(`/projects/${project.id}/${key}`)} key={key}>{label}</button>)}</nav>
        <main className="workspace-main">{data.loading ? <LoadingState label="프로젝트 데이터를 불러오는 중..."/> : <TabContent tab={tab} project={project} data={data} canEdit={canEdit} notify={notify} onUpload={openUpload} onFileDrop={requestUpload} uploadQueue={uploadQueue.filter(item => item.projectId === project.id)} onRetryUpload={scheduleUpload} onClearUploadQueue={() => setUploadQueue(current => current.filter(item => item.projectId !== project.id || ['QUEUED', 'UPLOADING'].includes(item.status)))} onDeleteProject={deleteCurrentProject} deleting={deleteMutation.isPending}/>}</main>
      </section>
    </div>
    <ProjectCreateModal open={creating} recentInvitees={recentInvitees} pending={createMutation.isPending} onClose={() => setCreating(false)} onSubmit={createNewProject}/>
    {uploadFiles.length > 0 && <DocumentUploadModal files={uploadFiles} uploading={false} onClose={() => setUploadFiles([])} onRemove={index => setUploadFiles(current => current.filter((_, currentIndex) => currentIndex !== index))} onSubmit={confirmUpload}/>}
  </div>
}

function TabContent({ tab, project, data, canEdit, notify, onUpload, onFileDrop, uploadQueue, onRetryUpload, onClearUploadQueue, onDeleteProject, deleting }) {
  if (tab === 'documents') return <DocumentsView projectId={project.id} documents={data.documents} canEdit={canEdit} onUpload={onUpload} onFileDrop={onFileDrop} uploadQueue={uploadQueue} onRetryUpload={onRetryUpload} onClearUploadQueue={onClearUploadQueue} onRetry={data.retryDocument} retryingDocumentId={data.retryingDocumentId}/>
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
  return <BoardView/>
}

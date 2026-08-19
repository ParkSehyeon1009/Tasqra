import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import BoardView from '../features/board/BoardView'
import DashboardView from '../features/dashboard/DashboardView'
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
const TABS = [['dashboard','대시보드'],['documents','문서'],['search','검색'],['board','보드'],['settings','설정']]

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
  const data = useWorkspaceData(project, notify)
  const fileInputRef = useRef(null)
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
  async function confirmUpload(files, extractionStrategy, documentType) {
    // 업로드 창은 파일 전송 완료를 기다리지 않고 즉시 닫는다. 이후 처리는
    // 별도로 보관한 목록을 사용하므로 사용자는 다른 화면에서 작업할 수 있다.
    const queuedFiles = [...files]
    setUploadFiles([])
    for (const file of queuedFiles) {
      try {
        await data.uploadFile(file, isImageUpload(file) ? 'AUTO' : extractionStrategy, documentType)
      } catch { /* 파일별 오류는 공통 토스트에서 처리하고 다음 파일을 계속 접수한다. */ }
    }
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
        <main className="workspace-main">{data.loading ? <LoadingState label="프로젝트 데이터를 불러오는 중..."/> : <TabContent tab={tab} project={project} data={data} canEdit={canEdit} onUpload={openUpload} onFileDrop={requestUpload} uploading={data.uploading} onDeleteProject={deleteCurrentProject} deleting={deleteMutation.isPending}/>}</main>
      </section>
    </div>
    <ProjectCreateModal open={creating} recentInvitees={recentInvitees} pending={createMutation.isPending} onClose={() => setCreating(false)} onSubmit={createNewProject}/>
    {uploadFiles.length > 0 && <DocumentUploadModal files={uploadFiles} uploading={data.uploading} onClose={() => setUploadFiles([])} onRemove={index => setUploadFiles(current => current.filter((_, currentIndex) => currentIndex !== index))} onSubmit={confirmUpload}/>}
  </div>
}

function TabContent({ tab, project, data, canEdit, onUpload, onFileDrop, uploading, onDeleteProject, deleting }) {
  if (tab === 'documents') return <DocumentsView projectId={project.id} documents={data.documents} canEdit={canEdit} onUpload={onUpload} onFileDrop={onFileDrop} uploading={uploading} uploadingFileName={data.uploadingFileName} onRetry={data.retryDocument} retryingDocumentId={data.retryingDocumentId}/>
  if (tab === 'settings') return <MembersView project={project} members={data.members} invitations={data.invitations} onUpdateProject={data.updateProject} updatingProject={data.updatingProject} onInvite={data.invite} onCancelInvitation={data.cancelInvitation} onRole={data.changeRole} onRemove={data.excludeMember} onDeleteProject={onDeleteProject} deleting={deleting}/>
  if (tab === 'dashboard') return <DashboardView projectId={project.id} documents={data.documents} members={data.members}/>
  // 검색은 워크스페이스 데이터(문서 목록 · 멤버)를 쓰지 않는다. 자기 상태만
  // 들고 api/search.js 를 부른다. 범위 토글에 쓸 프로젝트 이름만 넘긴다.
  if (tab === 'search') return <SearchView projectId={project.id} projectName={project.name}/>
  return <BoardView/>
}

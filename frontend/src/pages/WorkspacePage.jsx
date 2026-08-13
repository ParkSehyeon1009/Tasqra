import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import BoardView from '../features/board/BoardView'
import DashboardView from '../features/dashboard/DashboardView'
import DocumentsView from '../features/documents/DocumentsView'
import MembersView from '../features/members/MembersView'
import ProjectCreateModal from '../features/projects/ProjectCreateModal'
import ProjectSidebar from '../features/projects/ProjectSidebar'
import { useInvitationsQuery } from '../hooks/useInvitationsQuery'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import { useWorkspaceData } from '../hooks/useWorkspaceData'
import { clearRecentProjectId, setRecentProjectId } from '../utils/recentProject'
import '../styles/workspace.css'

const TABS = [['dashboard','대시보드'],['documents','문서'],['board','보드'],['settings','설정']]

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
  function requestUpload(file) {
    if (!file || !canEdit) return
    return data.uploadFile(file, 'AUTO')
  }
  async function upload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    try { await requestUpload(file) } catch { /* 공통 토스트에서 처리 */ }
    finally { event.target.value = '' }
  }
  async function deleteCurrentProject() {
    try {
      await deleteMutation.mutateAsync(project.id)
      clearRecentProjectId(user?.id, project.id)
      navigate('/projects', { replace: true })
    } catch { /* 공통 토스트에서 처리 */ }
  }

  return <div className="app-frame"><AppHeader user={user} onLogout={onLogout} notify={notify} project={project}/><input ref={fileInputRef} hidden type="file" accept=".pdf,.docx,.hwpx,.png,.jpg,.jpeg" onChange={upload}/>
    <div className="workspace-shell">
      <ProjectSidebar projects={projects} activeProjectId={project.id} onSelect={selected => navigate(`/projects/${selected.id}/dashboard`)} onCreate={() => setCreating(true)}/>
      <section className="workspace-content">
        <nav className="tabs" aria-label="프로젝트 메뉴">{TABS.map(([key,label]) => <button className={tab === key ? 'active' : ''} onClick={() => navigate(`/projects/${project.id}/${key}`)} key={key}>{label}</button>)}</nav>
        <main className="workspace-main">{data.loading ? <LoadingState label="프로젝트 데이터를 불러오는 중..."/> : <TabContent tab={tab} project={project} data={data} canEdit={canEdit} onUpload={openUpload} onFileDrop={requestUpload} uploading={data.uploading} onDeleteProject={deleteCurrentProject} deleting={deleteMutation.isPending}/>}</main>
      </section>
    </div>
    <ProjectCreateModal open={creating} recentInvitees={recentInvitees} pending={createMutation.isPending} onClose={() => setCreating(false)} onSubmit={createNewProject}/>
  </div>
}

function TabContent({ tab, project, data, canEdit, onUpload, onFileDrop, uploading, onDeleteProject, deleting }) {
  if (tab === 'documents') return <DocumentsView projectId={project.id} documents={data.documents} canEdit={canEdit} onUpload={onUpload} onFileDrop={onFileDrop} uploading={uploading} uploadingFileName={data.uploadingFileName}/>
  if (tab === 'settings') return <MembersView project={project} members={data.members} invitations={data.invitations} onUpdateProject={data.updateProject} updatingProject={data.updatingProject} onInvite={data.invite} onCancelInvitation={data.cancelInvitation} onRole={data.changeRole} onRemove={data.excludeMember} onDeleteProject={onDeleteProject} deleting={deleting}/>
  if (tab === 'dashboard') return <DashboardView projectId={project.id} documents={data.documents} members={data.members}/>
  return <BoardView/>
}

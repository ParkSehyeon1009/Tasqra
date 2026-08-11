import { useRef } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import BoardView from '../features/board/BoardView'
import DashboardView from '../features/dashboard/DashboardView'
import DocumentsView from '../features/documents/DocumentsView'
import MembersView from '../features/members/MembersView'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import { useWorkspaceData } from '../hooks/useWorkspaceData'
import '../styles/workspace.css'

const TABS = [['dashboard','대시보드'],['documents','문서'],['board','보드'],['settings','설정']]

export default function WorkspacePage({ user, onLogout, notify }) {
  const { projectId, tab } = useParams()
  const navigate = useNavigate()
  const { projects, loading, deleteMutation } = useProjectsQuery(notify)
  const project = projects.find(item => String(item.id) === projectId)
  if (!TABS.some(([key]) => key === tab)) return <Navigate to={`/projects/${projectId}/documents`} replace/>
  if (loading) return <LoadingState label="프로젝트를 불러오는 중..."/>
  if (!project) return <Navigate to="/projects" replace/>
  return <WorkspaceContent project={project} tab={tab} navigate={navigate} notify={notify} user={user} onLogout={onLogout} deleteMutation={deleteMutation}/>
}

function WorkspaceContent({ project, tab, navigate, notify, user, onLogout, deleteMutation }) {
  const data = useWorkspaceData(project, notify)
  const fileInputRef = useRef(null)
  const canEdit = project.role !== 'VIEWER'
  const openUpload = () => fileInputRef.current?.click()
  async function upload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    try { await data.uploadFile(file) } catch { /* 공통 토스트에서 처리 */ }
    finally { event.target.value = '' }
  }
  async function deleteCurrentProject() {
    try {
      await deleteMutation.mutateAsync(project.id)
      navigate('/projects', { replace: true })
    } catch { /* 공통 토스트에서 처리 */ }
  }
  return <div className="app-frame"><AppHeader user={user} onLogout={onLogout} notify={notify} project={project}/><input ref={fileInputRef} hidden type="file" onChange={upload}/>
    <nav className="tabs">{TABS.map(([key,label]) => <button className={tab === key ? 'active' : ''} onClick={() => navigate(`/projects/${project.id}/${key}`)} key={key}>{label}</button>)}</nav>
    <main className="workspace-main">{data.loading ? <LoadingState label="프로젝트 데이터를 불러오는 중..."/> : <TabContent tab={tab} project={project} data={data} canEdit={canEdit} onUpload={openUpload} onDeleteProject={deleteCurrentProject} deleting={deleteMutation.isPending}/>}</main>
  </div>
}

function TabContent({ tab, project, data, canEdit, onUpload, onDeleteProject, deleting }) {
  if (tab === 'documents') return <DocumentsView documents={data.documents} canEdit={canEdit} onUpload={onUpload}/>
  if (tab === 'settings') return <MembersView members={data.members} role={project.role} onInvite={data.invite} onRole={data.changeRole} onRemove={data.excludeMember} onDeleteProject={onDeleteProject} deleting={deleting}/>
  if (tab === 'dashboard') return <DashboardView documents={data.documents} members={data.members}/>
  return <BoardView/>
}

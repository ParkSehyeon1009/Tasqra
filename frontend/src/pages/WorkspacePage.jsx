import { useRef } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import Logo from '../components/common/Logo'
import LoadingState from '../components/common/LoadingState'
import BoardView from '../features/board/BoardView'
import DashboardView from '../features/dashboard/DashboardView'
import DocumentsView from '../features/documents/DocumentsView'
import MembersView from '../features/members/MembersView'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import { useWorkspaceData } from '../hooks/useWorkspaceData'
import '../styles/workspace.css'

const TABS = [['dashboard','대시보드'],['documents','문서'],['board','보드'],['settings','설정']]

export default function WorkspacePage({ notify }) {
  const { projectId, tab } = useParams()
  const navigate = useNavigate()
  const { projects, loading: projectsLoading } = useProjectsQuery(notify)
  const project = projects.find(item => String(item.id) === projectId)

  if (!TABS.some(([key]) => key === tab)) return <Navigate to={`/projects/${projectId}/documents`} replace/>
  if (projectsLoading) return <LoadingState label="프로젝트를 불러오는 중..."/>
  if (!project) return <Navigate to="/projects" replace/>
  return <WorkspaceContent project={project} tab={tab} navigate={navigate} notify={notify}/>
}

function WorkspaceContent({ project, tab, navigate, notify }) {
  const data = useWorkspaceData(project, notify)
  const fileInputRef = useRef(null)
  const canEdit = project.role !== 'VIEWER'
  const openUpload = () => fileInputRef.current?.click()
  async function upload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    try { await data.uploadFile(file) } catch { /* mutation 알림 사용 */ }
    finally { event.target.value = '' }
  }
  return <div className="app-frame"><WorkspaceHeader project={project} members={data.members} onBack={() => navigate('/projects')} canEdit={canEdit} onUpload={openUpload}/>
    <input ref={fileInputRef} hidden type="file" onChange={upload}/>
    <nav className="tabs">{TABS.map(([key,label]) => <button className={tab === key ? 'active' : ''} onClick={() => navigate(`/projects/${project.id}/${key}`)} key={key}>{label}</button>)}</nav>
    <main className="workspace-main">{data.loading ? <LoadingState label="프로젝트 데이터를 불러오는 중..."/> : <TabContent tab={tab} project={project} data={data} canEdit={canEdit} onUpload={openUpload}/>}</main>
  </div>
}

function WorkspaceHeader({ project, members, onBack, canEdit, onUpload }) {
  return <header className="project-header"><button className="brand-button" onClick={onBack}><Logo/></button><span className="slash">/</span><strong>{project.name}</strong><span className="status-pill">진행 중</span><div className="header-spacer"/><div className="avatars">{members.slice(0, 3).map(member => <i key={member.id}>{member.name.slice(0, 1)}</i>)}</div><button className="primary" onClick={onUpload} disabled={!canEdit}>문서 업로드</button></header>
}

function TabContent({ tab, project, data, canEdit, onUpload }) {
  if (tab === 'documents') return <DocumentsView documents={data.documents} canEdit={canEdit} onUpload={onUpload}/>
  if (tab === 'settings') return <MembersView members={data.members} role={project.role} onInvite={data.invite} onRole={data.changeRole} onRemove={data.excludeMember}/>
  if (tab === 'dashboard') return <DashboardView documents={data.documents} members={data.members}/>
  return <BoardView/>
}

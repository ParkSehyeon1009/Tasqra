import { useState } from 'react'
import Logo from '../components/common/Logo'
import BoardView from '../features/board/BoardView'
import DashboardView from '../features/dashboard/DashboardView'
import DocumentsView from '../features/documents/DocumentsView'
import MembersView from '../features/members/MembersView'
import { useWorkspaceData } from '../hooks/useWorkspaceData'
import '../styles/workspace.css'

const TABS = [['dashboard','대시보드'],['documents','문서'],['board','보드'],['settings','설정']]

export default function WorkspacePage({ project, onBack, notify }) {
  const [tab, setTab] = useState('documents')
  const { members, documents, loading, fileInputRef, invite, changeRole, excludeMember, upload } = useWorkspaceData(project, notify)
  const canEdit = project.role !== 'VIEWER'
  const openUpload = () => fileInputRef.current?.click()

  return <div className="app-frame"><WorkspaceHeader project={project} members={members} onBack={onBack} canEdit={canEdit} onUpload={openUpload}/>
    <input ref={fileInputRef} hidden type="file" onChange={upload}/>
    <nav className="tabs">{TABS.map(([key,label]) => <button className={tab === key ? 'active' : ''} onClick={() => setTab(key)} key={key}>{label}</button>)}</nav>
    <main className="workspace-main">{loading ? <div className="empty-card">불러오는 중...</div> : <WorkspaceContent tab={tab} project={project} members={members} documents={documents} invite={invite} changeRole={changeRole} excludeMember={excludeMember} canEdit={canEdit} onUpload={openUpload}/>}</main>
  </div>
}

function WorkspaceHeader({ project, members, onBack, canEdit, onUpload }) {
  return <header className="project-header"><button className="brand-button" onClick={onBack}><Logo/></button><span className="slash">/</span><strong>{project.name}</strong><span className="status-pill">진행 중</span><div className="header-spacer"/><div className="avatars">{members.slice(0, 3).map(member => <i key={member.id}>{member.name.slice(0, 1)}</i>)}</div><button className="primary" onClick={onUpload} disabled={!canEdit}>문서 업로드</button></header>
}

function WorkspaceContent({ tab, project, members, documents, invite, changeRole, excludeMember, canEdit, onUpload }) {
  if (tab === 'documents') return <DocumentsView documents={documents} canEdit={canEdit} onUpload={onUpload}/>
  if (tab === 'settings') return <MembersView members={members} role={project.role} onInvite={invite} onRole={changeRole} onRemove={excludeMember}/>
  if (tab === 'dashboard') return <DashboardView documents={documents} members={members}/>
  return <BoardView/>
}

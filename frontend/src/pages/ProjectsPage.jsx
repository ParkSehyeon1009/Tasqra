import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import ProjectCreateModal from '../features/projects/ProjectCreateModal'
import { useInvitationsQuery } from '../hooks/useInvitationsQuery'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import '../styles/projects.css'

export default function ProjectsPage({ user, onLogout, notify }) {
  const [creating, setCreating] = useState(false)
  const navigate = useNavigate()
  const { projects, loading, error, createMutation } = useProjectsQuery(notify)
  const { recentInvitees } = useInvitationsQuery(Boolean(user), notify)

  async function submit(values) {
    try {
      const { project } = await createMutation.mutateAsync(values)
      setCreating(false)
      navigate(`/projects/${project.id}/documents`)
    } catch { /* 공통 토스트에서 처리 */ }
  }

  return <div className="project-screen"><AppHeader user={user} onLogout={onLogout} notify={notify}/>
    <main className="project-main"><div className="project-title"><div><h1>내 프로젝트</h1><p>문서와 팀 작업을 한곳에서 관리하세요.</p></div><button className="primary" onClick={() => setCreating(true)}>+ 새 프로젝트</button></div>
      {loading ? <LoadingState label="프로젝트를 불러오는 중..."/> : error ? <div className="error-state">{error.message}</div> : <div className="project-cards">{projects.map(project => <ProjectCard project={project} onClick={() => navigate(`/projects/${project.id}/documents`)} key={project.id}/>)}<button className="project-card project-card--new" onClick={() => setCreating(true)}><b>＋</b><strong>새 프로젝트 만들기</strong><span>문서를 모아둘 작업 공간을 만듭니다.</span></button></div>}
      {!loading && !projects.length && <div className="empty-card"><h2>첫 프로젝트를 만들어 보세요.</h2></div>}
    </main>
    <ProjectCreateModal open={creating} recentInvitees={recentInvitees} pending={createMutation.isPending} onClose={() => setCreating(false)} onSubmit={submit}/>
  </div>
}

function ProjectCard({ project, onClick }) {
  return <button className="project-card" onClick={onClick}><div><h2>{project.name}</h2><span className="status-pill">{project.status === 'ACTIVE' ? '진행 중' : '보관됨'}</span></div><p>{project.description || '프로젝트 문서와 팀 작업을 한곳에서 관리합니다.'}</p><dl><div><dt>권한</dt><dd>{project.role}</dd></div><div><dt>상태</dt><dd>{project.status}</dd></div></dl><small>{new Date(project.created_at).toLocaleDateString()} 생성</small></button>
}

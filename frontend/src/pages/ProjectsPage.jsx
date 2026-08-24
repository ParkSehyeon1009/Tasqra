import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import ProjectCreateModal from '../features/projects/ProjectCreateModal'
import ProjectSidebar from '../features/projects/ProjectSidebar'
import { useInvitationsQuery } from '../hooks/useInvitationsQuery'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import { getRecentProjectId, setRecentProjectId } from '../utils/recentProject'
import '../styles/projects.css'

export default function ProjectsPage({ user, onLogout, notify }) {
  const [creating, setCreating] = useState(false)
  const navigate = useNavigate()
  const { projects, loading, error, createMutation } = useProjectsQuery(notify)
  const { recentInvitees } = useInvitationsQuery(user?.id, notify)

  async function submit(values) {
    try {
      const { project } = await createMutation.mutateAsync(values)
      setCreating(false)
      setRecentProjectId(user?.id, project.id)
      navigate(`/projects/${project.id}/dashboard`)
    } catch { /* 공통 토스트에서 처리 */ }
  }

  if (loading) return <div className="project-screen"><AppHeader user={user} onLogout={onLogout} notify={notify}/><LoadingState label="프로젝트를 불러오는 중..."/></div>
  if (!error && projects.length) {
    const recentId = getRecentProjectId(user?.id)
    const target = projects.find(project => String(project.id) === recentId) ?? projects[0]
    return <Navigate to={`/projects/${target.id}/dashboard`} replace/>
  }

  return <div className="app-frame"><AppHeader user={user} onLogout={onLogout} notify={notify}/>
    <div className="workspace-shell">
      <ProjectSidebar projects={[]} onCreate={() => setCreating(true)} onSelect={() => {}} onNavigateTab={() => {}}/>
      <main className="project-empty-main">
        {error ? <div className="error-state">{error.message}</div> : <section className="project-empty-state"><span aria-hidden="true">＋</span><h1>아직 참여 중인 프로젝트가 없습니다.</h1><p>새 프로젝트를 만들어 문서와 작업을 한곳에서 관리해 보세요.</p><button className="primary" onClick={() => setCreating(true)}>새 프로젝트 만들기</button></section>}
      </main>
    </div>
    <ProjectCreateModal open={creating} recentInvitees={recentInvitees} pending={createMutation.isPending} onClose={() => setCreating(false)} onSubmit={submit}/>
  </div>
}

// =============================================================================
// 이 파일의 책임: 로그인 직후 전역 메인 대시보드와 공통 프로젝트 사이드바를 조립한다.
// 다른 파일과의 관계: PortfolioDashboard에 실제 프로젝트 데이터를 전달하고 생성 후
//   기존 프로젝트 작업공간으로 이동한다.
// Spring 비교: 전역 대시보드 View와 프로젝트 생성 흐름을 조립하는 MVC Controller다.
// =============================================================================

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import PortfolioDashboard from '../features/projects/PortfolioDashboard'
import ProjectCreateModal from '../features/projects/ProjectCreateModal'
import ProjectSidebar from '../features/projects/ProjectSidebar'
import { useInvitationsQuery } from '../hooks/useInvitationsQuery'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import { setRecentProjectId } from '../utils/recentProject'
import '../styles/projects.css'

export default function ProjectsPage({ user, onLogout, notify }) {
  const [creating, setCreating] = useState(false)
  const navigate = useNavigate()
  const { projects, loading, error, createMutation } = useProjectsQuery(notify)
  const invitationData = useInvitationsQuery(user?.id, notify)

  async function submit(values) {
    try {
      const { project } = await createMutation.mutateAsync(values)
      setCreating(false)
      setRecentProjectId(user?.id, project.id)
      navigate(`/projects/${project.id}/dashboard`)
    } catch { /* 공통 토스트에서 처리 */ }
  }

  return <div className="app-frame projects-home">
    <AppHeader user={user} onLogout={onLogout} notify={notify} section="전체 프로젝트"/>
    <div className="workspace-shell">
      <ProjectSidebar
        projects={projects}
        activeProjectId={null}
        activeTab={null}
        portfolioActive
        onOpenPortfolio={() => navigate('/projects')}
        onSelect={project => navigate(`/projects/${project.id}/dashboard`)}
        onNavigateTab={() => {}}
        onCreate={() => setCreating(true)}
      />
      <section className="workspace-content">
        {loading
          ? <main className="workspace-main"><LoadingState label="프로젝트를 불러오는 중..."/></main>
          : error
            ? <main className="workspace-main projects-error"><div className="error-state">{error.message}</div></main>
            : <PortfolioDashboard user={user} projects={projects} invitations={invitationData.invitations} onCreate={() => setCreating(true)}/>}
      </section>
    </div>
    <ProjectCreateModal open={creating} recentInvitees={invitationData.recentInvitees} pending={createMutation.isPending} onClose={() => setCreating(false)} onSubmit={submit}/>
  </div>
}

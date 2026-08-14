export default function ProjectSidebar({ projects, activeProjectId, onSelect, onCreate }) {
  return <aside className="project-sidebar" aria-label="프로젝트 전환">
    <div className="project-sidebar__heading"><span>프로젝트</span><strong>{projects.length}</strong></div>
    <nav className="project-sidebar__list" aria-label="참여 중인 프로젝트">
      {projects.length ? projects.map((project, index) => {
        const active = String(project.id) === String(activeProjectId)
        return <button className={active ? 'is-active' : ''} aria-current={active ? 'page' : undefined} onClick={() => onSelect(project)} key={project.id}>
          <i className={`project-sidebar__marker marker-${index % 5}`} aria-hidden="true"/><span>{project.name}</span>{project.status === 'ARCHIVED' && <small>보관됨</small>}
        </button>
      }) : <p>참여 중인 프로젝트가 없습니다.</p>}
    </nav>
    <button className="project-sidebar__create" onClick={onCreate}><span aria-hidden="true">＋</span> 새 프로젝트 만들기</button>
  </aside>
}

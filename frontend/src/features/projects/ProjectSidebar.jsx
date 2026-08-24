const PROJECT_MENUS = [
  ['dashboard', '▦', '대시보드'],
  ['documents', '▤', '문서'],
  ['search', '⌕', '검색'],
  ['deliverables', '⇩', '산출물'],
  ['board', '▥', '보드'],
  ['settings', '⚙', '설정'],
]

export default function ProjectSidebar({ projects, activeProjectId, activeTab, onSelect, onNavigateTab, onCreate }) {
  return <aside className="project-sidebar" aria-label="프로젝트 메뉴">
    <div className="project-sidebar__brand"><span aria-hidden="true">T</span><div><strong>Tasqra</strong><small>DOCUMENT · TO · ACTION</small></div></div>
    <div className="project-sidebar__heading"><span>프로젝트</span><button onClick={onCreate} aria-label="새 프로젝트 만들기">＋</button></div>
    <nav className="project-sidebar__list" aria-label="참여 중인 프로젝트">
      {projects.length ? projects.map((project, index) => {
        const active = String(project.id) === String(activeProjectId)
        return <div className={`project-sidebar__project${active ? ' is-open' : ''}`} key={project.id}>
          <button className="project-sidebar__project-button" aria-current={active ? 'page' : undefined} onClick={() => onSelect(project)}>
            <i className={`project-sidebar__marker marker-${index % 5}`} aria-hidden="true"/><span>{project.name}</span>{project.status === 'ARCHIVED' ? <small>보관</small> : <b aria-hidden="true">⌄</b>}
          </button>
          {active && <div className="project-sidebar__menus">{PROJECT_MENUS.map(([key, icon, label]) => <button className={activeTab === key ? 'is-active' : ''} aria-current={activeTab === key ? 'page' : undefined} onClick={() => onNavigateTab(key)} key={key}><i aria-hidden="true">{icon}</i><span>{label}</span></button>)}</div>}
        </div>
      }) : <p>참여 중인 프로젝트가 없습니다.</p>}
    </nav>
  </aside>
}

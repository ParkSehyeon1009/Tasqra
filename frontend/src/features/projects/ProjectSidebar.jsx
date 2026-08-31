import { useEffect, useState } from 'react'

// 탭이 **두 곳**에 적혀 있다. 여기와 WorkspacePage 의 TABS 다.
//   · 이 배열 = 사이드바에서 눌러 들어갈 수 있는 곳
//   · TABS = 주소로 들어왔을 때 허용되는 곳 (없으면 대시보드로 되돌린다)
// 한쪽만 고치면 **에러 없이** 어긋난다 — 여기만 넣으면 눌러도 대시보드로
// 튕기고, TABS 에만 넣으면 주소를 직접 쳐야 들어갈 수 있다.
const PROJECT_MENUS = [['dashboard','dashboard','대시보드'],['documents','document','문서'],['search','search','검색'],['board','board','보드'],['amounts','amount','금액'],['decisions','decision','결정·일정'],['deliverables','deliverable','산출물'],['settings','settings','설정']]

export default function ProjectSidebar({ projects, activeProjectId, activeTab, onSelect, onNavigateTab, onCreate }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('tasqra-rail-collapsed') === '1')
  useEffect(() => {
    document.body.classList.toggle('tasqra-rail-mini', collapsed)
    localStorage.setItem('tasqra-rail-collapsed', collapsed ? '1' : '0')
    return () => document.body.classList.remove('tasqra-rail-mini')
  }, [collapsed])
  return <aside className="project-sidebar" aria-label="프로젝트 메뉴">
    <div className="project-sidebar__top"><div className="project-sidebar__brand"><BrandMark/><div className="project-sidebar__text"><strong>Tasqra</strong><small>DOCUMENT · TO · ACTION</small></div></div><button className="project-sidebar__collapse" onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? '사이드바 펼치기' : '사이드바 접기'}><Icon name="chevron"/></button></div>
    <div className="project-sidebar__heading"><span className="project-sidebar__text">프로젝트</span><button onClick={onCreate} aria-label="새 프로젝트 만들기">＋</button></div>
    <nav className="project-sidebar__list" aria-label="참여 중인 프로젝트">{projects.length ? projects.map((project,index) => {
      const active = String(project.id) === String(activeProjectId)
      return <div className={`project-sidebar__project${active ? ' is-open' : ''}`} key={project.id}><button className="project-sidebar__project-button" aria-current={active ? 'page' : undefined} title={project.name} onClick={() => onSelect(project)}><i className={`project-sidebar__marker marker-${index % 5}`} aria-hidden="true"/><span className="project-sidebar__text">{project.name}</span>{project.status === 'ARCHIVED' ? <small className="project-sidebar__text">보관</small> : <b className="project-sidebar__text" aria-hidden="true"><Icon name="chevron"/></b>}</button>{active && <div className="project-sidebar__menus">{PROJECT_MENUS.map(([key,icon,label]) => <button className={activeTab === key ? 'is-active' : ''} aria-current={activeTab === key ? 'page' : undefined} title={label} onClick={() => onNavigateTab(key)} key={key}><Icon name={icon}/><span className="project-sidebar__text">{label}</span></button>)}</div>}</div>
    }) : <p className="project-sidebar__text">참여 중인 프로젝트가 없습니다.</p>}</nav>
  </aside>
}

function BrandMark() { return <svg className="project-sidebar__logo" width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><defs><linearGradient id="tasqra-logo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#7fb3ff"/><stop offset="1" stopColor="#3f5bd9"/></linearGradient></defs><circle cx="16" cy="15" r="9.5" fill="url(#tasqra-logo)"/><ellipse cx="16" cy="16" rx="14.5" ry="5.6" fill="none" stroke="#9fc2ff" strokeWidth="1.5" opacity=".85" transform="rotate(-22 16 16)"/><path d="M11.4 11.2h9.2M16 11.2v9.6" stroke="#fff" strokeWidth="2.4" strokeLinecap="round"/><circle cx="26" cy="7" r="1.1" fill="#cfe1ff"/><circle cx="6" cy="24" r=".8" fill="#cfe1ff"/></svg> }

function Icon({ name }) {
  const common = { width:16,height:16,viewBox:'0 0 20 20',fill:'none',stroke:'currentColor',strokeWidth:1.7,'aria-hidden':true }
  if(name==='dashboard') return <svg {...common}><rect x="2.5" y="2.5" width="6" height="6" rx="1.4"/><rect x="11.5" y="2.5" width="6" height="6" rx="1.4"/><rect x="2.5" y="11.5" width="6" height="6" rx="1.4"/><rect x="11.5" y="11.5" width="6" height="6" rx="1.4"/></svg>
  if(name==='document') return <svg {...common}><path d="M5 2.5h6l4 4v11H5z"/><path d="M11 2.5v4h4"/></svg>
  if(name==='search') return <svg {...common}><circle cx="9" cy="9" r="5.5"/><path d="M13.2 13.2 17 17"/></svg>
  if(name==='deliverable') return <svg {...common}><path d="M3 16V9m4.7 7V4.5M12.3 16v-5M17 16V7"/></svg>
  // 금액은 원화 기호(₩)로 둔다 — 동전·지폐 그림은 16px 에서 뭉개진다.
  if(name==='amount') return <svg {...common}><path d="M5.6 5l2.4 5 2-3.4 2 3.4 2.4-5"/><path d="M3.6 11.4h12.8M3.6 14h12.8"/></svg>
  if(name==='decision') return <svg {...common}><path d="M4 3.5h12v13H4z"/><path d="m6.5 9 2 2 5-5M6.5 14h7"/></svg>
  if(name==='board') return <svg {...common}><rect x="2.5" y="3" width="4.5" height="14" rx="1.2"/><rect x="8.7" y="3" width="4.5" height="9" rx="1.2"/><rect x="14.9" y="3" width="2.6" height="12" rx="1.2"/></svg>
  if(name==='settings') return <svg {...common}><circle cx="10" cy="10" r="2.6"/><path d="M10 2.6v2M10 15.4v2M2.6 10h2M15.4 10h2M4.8 4.8l1.4 1.4M13.8 13.8l1.4 1.4M15.2 4.8l-1.4 1.4M6.2 13.8l-1.4 1.4"/></svg>
  return <svg {...common}><path d="M12 5l-5 5 5 5"/></svg>
}

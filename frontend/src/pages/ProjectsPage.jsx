import { useState } from 'react'
import Logo from '../components/common/Logo'
import '../styles/projects.css'

export default function ProjectsPage({ user, projects, onCreate, onSelect, onLogout }) {
  const [creating, setCreating] = useState(false)
  async function submit(event) { if (await onCreate(event)) setCreating(false) }

  return <div className="project-screen"><header className="global-header"><Logo/><div className="user-chip"><span>{user.name}</span><i>{user.name.slice(0, 1)}</i><button onClick={onLogout}>로그아웃</button></div></header>
    <main className="project-main"><div className="project-title"><div><h1>내 프로젝트</h1><p>문서를 올리고 팀과 함께 정리할 공간을 선택하세요.</p></div><button className="primary" onClick={() => setCreating(true)}>새 프로젝트</button></div>
      {creating && <form className="create-project" onSubmit={submit}><input name="name" placeholder="프로젝트 이름" required autoFocus/><input name="description" placeholder="프로젝트 설명 (선택)"/><button className="primary">프로젝트 만들기</button><button type="button" onClick={() => setCreating(false)}>취소</button></form>}
      <div className="project-cards">{projects.map(project => <ProjectCard project={project} onClick={() => onSelect(project)} key={project.id}/>)}
        <button className="project-card project-card--new" onClick={() => setCreating(true)}><b>＋</b><strong>새 프로젝트 만들기</strong><span>문서를 모아둘 공간을 만듭니다.</span></button>
      </div>{!projects.length && <div className="empty-card"><b>＋</b><h2>첫 프로젝트를 만들어 보세요.</h2></div>}
    </main></div>
}

function ProjectCard({ project, onClick }) {
  return <button className="project-card" onClick={onClick}><div><h2>{project.name}</h2><span className="status-pill">{project.status === 'ACTIVE' ? '진행 중' : '보관됨'}</span></div><p>{project.description || '프로젝트 문서와 팀원을 한곳에서 관리합니다.'}</p><dl><div><dt>권한</dt><dd>{project.role}</dd></div><div><dt>상태</dt><dd>{project.status}</dd></div></dl><small>{new Date(project.created_at).toLocaleDateString()} 생성</small></button>
}

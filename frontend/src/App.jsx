import { useEffect, useState } from 'react'
import { createProject, addMember, listMembers, listProjectDocuments, listProjects, removeMember, updateMember, uploadProjectDocument } from './api/project'
import { getMe, login, signup } from './api/auth'
import './App.css'

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault(); setError('')
    const values = Object.fromEntries(new FormData(event.currentTarget))
    try {
      const result = await (mode === 'login' ? login(values) : signup(values))
      localStorage.setItem('tasqra_token', result.access_token); onAuthenticated(result.user)
    } catch (err) { setError(err.message) }
  }
  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}>
    <div className="brand">Tasqra</div><h1>{mode === 'login' ? '로그인' : '회원가입'}</h1>
    {mode === 'signup' && <input name="name" placeholder="표시 이름" required />}
    <input name="login_id" placeholder="아이디" minLength="3" pattern="[a-zA-Z0-9_.-]+" required />
    {mode === 'signup' && <input name="email" type="email" placeholder="이메일" required />}
    <input name="password" type="password" placeholder="비밀번호 (8자 이상)" minLength="8" required />
    {error && <p className="error">{error}</p>}<button className="primary">{mode === 'login' ? '로그인' : '가입하기'}</button>
    <button type="button" className="link" onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}>{mode === 'login' ? '계정 만들기' : '로그인으로 돌아가기'}</button>
  </form></main>
}

function Workspace({ user, onLogout }) {
  const [projects, setProjects] = useState([]), [selected, setSelected] = useState(null)
  const [members, setMembers] = useState([]), [documents, setDocuments] = useState([]), [error, setError] = useState('')
  async function refreshProjects() { const rows = await listProjects(); setProjects(rows); if (!selected && rows[0]) setSelected(rows[0]) }
  async function refreshProject() { if (!selected) return; const [m, d] = await Promise.all([listMembers(selected.id), listProjectDocuments(selected.id)]); setMembers(m); setDocuments(d.items) }
  useEffect(() => {
    listProjects().then(rows => { setProjects(rows); setSelected(current => current || rows[0] || null) }).catch(e => setError(e.message))
  }, [])
  useEffect(() => {
    if (!selected) return
    Promise.all([listMembers(selected.id), listProjectDocuments(selected.id)]).then(([m, d]) => { setMembers(m); setDocuments(d.items) }).catch(e => setError(e.message))
  }, [selected])
  async function create(event) { event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); const project = await createProject(values); event.currentTarget.reset(); await refreshProjects(); setSelected(project) }
  async function invite(event) { event.preventDefault(); const values = Object.fromEntries(new FormData(event.currentTarget)); await addMember(selected.id, values); event.currentTarget.reset(); await refreshProject() }
  async function upload(event) { const file = event.target.files[0]; if (!file) return; await uploadProjectDocument(selected.id, file); event.target.value = ''; await refreshProject() }
  return <div className="workspace"><aside><div className="brand">Tasqra</div><p className="muted">{user.name}</p><h3>내 프로젝트</h3>
    <nav>{projects.map(p => <button className={selected?.id === p.id ? 'active' : ''} key={p.id} onClick={() => setSelected(p)}>{p.name}<small>{p.role}</small></button>)}</nav>
    <form className="compact" onSubmit={create}><input name="name" placeholder="새 프로젝트" required/><button>추가</button></form><button className="link logout" onClick={onLogout}>로그아웃</button></aside>
    <main className="content">{error && <p className="error">{error}</p>}{!selected ? <section className="empty"><h1>프로젝트를 만들어 시작하세요</h1></section> : <>
      <header><div><p className="eyebrow">PROJECT WORKSPACE</p><h1>{selected.name}</h1><p>{selected.description || '프로젝트 문서와 팀원을 한곳에서 관리합니다.'}</p></div><span className="role">{selected.role}</span></header>
      <div className="grid"><section className="panel"><div className="panel-head"><h2>문서</h2>{selected.role !== 'VIEWER' && <label className="upload">업로드<input type="file" onChange={upload}/></label>}</div>
        {documents.length ? <ul className="list">{documents.map(d => <li key={d.id}><div><strong>{d.filename}</strong><small>{d.status} · {d.document_type || '미분류'}</small></div><time>{new Date(d.created_at).toLocaleDateString()}</time></li>)}</ul> : <p className="muted">아직 문서가 없습니다.</p>}</section>
      <section className="panel"><div className="panel-head"><h2>팀원</h2><span>{members.length}명</span></div>
        {selected.role === 'OWNER' && <form className="invite" onSubmit={invite}><input name="login_id" placeholder="팀원 아이디" required/><select name="role"><option>EDITOR</option><option>VIEWER</option></select><button>추가</button></form>}
        <ul className="list">{members.map(m => <li key={m.id}><div><strong>{m.name}</strong><small>@{m.login_id}</small></div>{selected.role === 'OWNER' && m.role !== 'OWNER' ? <div className="member-actions"><select value={m.role} onChange={async e => { await updateMember(selected.id, m.user_id, e.target.value); refreshProject() }}><option>EDITOR</option><option>VIEWER</option></select><button onClick={async () => { await removeMember(selected.id, m.user_id); refreshProject() }}>제외</button></div> : <span className="role">{m.role}</span>}</li>)}</ul></section></div></>}</main></div>
}

export default function App() {
  const [user, setUser] = useState(null), [loading, setLoading] = useState(Boolean(localStorage.getItem('tasqra_token')))
  useEffect(() => {
    const token = localStorage.getItem('tasqra_token')
    if (token) getMe().then(setUser).finally(() => setLoading(false))
    else queueMicrotask(() => setLoading(false))
    const logout = () => { setUser(null); setLoading(false) }
    window.addEventListener('tasqra:unauthorized', logout)
    return () => window.removeEventListener('tasqra:unauthorized', logout)
  }, [])
  if (loading) return <div className="center">불러오는 중...</div>
  if (!user) return <AuthScreen onAuthenticated={setUser}/>
  return <Workspace user={user} onLogout={() => { localStorage.removeItem('tasqra_token'); setUser(null) }}/>
}

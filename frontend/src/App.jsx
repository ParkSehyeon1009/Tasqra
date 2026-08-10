import { useCallback, useEffect, useRef, useState } from 'react'
import { addMember, createProject, listMembers, listProjectDocuments, listProjects, removeMember, updateMember, uploadProjectDocument } from './api/project'
import { getMe, login, signup } from './api/auth'
import './App.css'

const FALLBACK_ERROR = '요청 처리 중 오류가 발생했습니다.'

function Toast({ toast, onClose }) {
  if (!toast) return null
  return <div className={`toast toast--${toast.type}`} role="status">
    <span className="toast__icon">{toast.type === 'success' ? '✓' : '!'}</span>
    <div><strong>{toast.title}</strong><p>{toast.message}</p></div>
    <button onClick={onClose} aria-label="알림 닫기">×</button>
  </div>
}

function AuthScreen({ onAuthenticated, notify }) {
  const [mode, setMode] = useState('login')
  const [signupComplete, setSignupComplete] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault(); setBusy(true)
    const form = event.currentTarget
    const values = Object.fromEntries(new FormData(form))
    try {
      if (mode === 'signup') {
        await signup(values)
        form.reset(); setSignupComplete(true); setMode('login')
        notify('success', '회원가입 완료', '가입이 완료되었습니다. 아이디로 로그인해 주세요.')
        return
      }
      const result = await login(values)
      localStorage.setItem('tasqra_token', result.access_token)
      onAuthenticated(result.user)
      notify('success', '로그인 완료', `${result.user.name}님, 환영합니다.`)
    } catch (error) {
      notify('error', '요청 실패', error.message || FALLBACK_ERROR)
    } finally { setBusy(false) }
  }

  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}>
    <Logo /><div><p className="eyebrow">DOCUMENT WORKSPACE</p><h1>{mode === 'login' ? '로그인' : '회원가입'}</h1></div>
    {signupComplete && mode === 'login' && <div className="success-box"><strong>회원가입이 완료되었습니다.</strong><span>등록한 아이디와 비밀번호로 로그인하세요.</span></div>}
    {mode === 'signup' && <input name="name" placeholder="표시 이름" required />}
    <input name="login_id" placeholder="아이디" minLength="3" pattern="[a-zA-Z0-9_.-]+" required />
    {mode === 'signup' && <input name="email" type="email" placeholder="이메일" required />}
    <input name="password" type="password" placeholder="비밀번호 (8자 이상)" minLength="8" required />
    <button className="primary" disabled={busy}>{busy ? '처리 중...' : mode === 'login' ? '로그인' : '가입 완료'}</button>
    <button type="button" className="link" onClick={() => { setSignupComplete(false); setMode(mode === 'login' ? 'signup' : 'login') }}>{mode === 'login' ? '계정 만들기' : '로그인으로 돌아가기'}</button>
  </form></main>
}

function Logo() { return <div className="logo"><span>TQ</span><strong>Tasqra</strong></div> }

function ProjectsScreen({ user, projects, onCreate, onSelect, onLogout }) {
  const [creating, setCreating] = useState(false)
  return <div className="project-screen"><header className="global-header"><Logo/><div className="user-chip"><span>{user.name}</span><i>{user.name.slice(0, 1)}</i><button onClick={onLogout}>로그아웃</button></div></header>
    <main className="project-main"><div className="project-title"><div><h1>내 프로젝트</h1><p>문서를 올리고 팀과 함께 정리할 공간을 선택하세요.</p></div><button className="primary" onClick={() => setCreating(true)}>새 프로젝트</button></div>
      {creating && <form className="create-project" onSubmit={async event => { if (await onCreate(event)) setCreating(false) }}><input name="name" placeholder="프로젝트 이름" required autoFocus/><input name="description" placeholder="프로젝트 설명 (선택)"/><button className="primary">프로젝트 만들기</button><button type="button" onClick={() => setCreating(false)}>취소</button></form>}
      <div className="project-cards">{projects.map(project => <button className="project-card" key={project.id} onClick={() => onSelect(project)}><div><h2>{project.name}</h2><span className="status-pill">{project.status === 'ACTIVE' ? '진행 중' : '보관됨'}</span></div><p>{project.description || '프로젝트 문서와 팀원을 한곳에서 관리합니다.'}</p><dl><div><dt>권한</dt><dd>{project.role}</dd></div><div><dt>상태</dt><dd>{project.status}</dd></div></dl><small>{new Date(project.created_at).toLocaleDateString()} 생성</small></button>)}
        <button className="project-card project-card--new" onClick={() => setCreating(true)}><b>＋</b><strong>새 프로젝트 만들기</strong><span>문서를 모아둘 공간을 만듭니다.</span></button>
      </div>{!projects.length && <div className="empty-card"><b>＋</b><h2>첫 프로젝트를 만들어 보세요.</h2></div>}
    </main></div>
}

function Workspace({ project, onBack, notify }) {
  const [tab, setTab] = useState('documents')
  const [members, setMembers] = useState([]), [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const fileRef = useRef(null)

  useEffect(() => {
    Promise.all([listMembers(project.id), listProjectDocuments(project.id)])
      .then(([nextMembers, nextDocuments]) => { setMembers(nextMembers); setDocuments(nextDocuments.items) })
      .catch(error => notify('error', '불러오기 실패', error.message || FALLBACK_ERROR))
      .finally(() => setLoading(false))
  }, [project.id, notify])

  async function invite(event) {
    event.preventDefault(); const form = event.currentTarget; const values = Object.fromEntries(new FormData(form))
    try { const member = await addMember(project.id, values); setMembers(current => [...current, member]); form.reset(); notify('success', '팀원 추가 완료', `${member.name}님을 ${member.role} 권한으로 추가했습니다.`) }
    catch (error) { notify('error', '팀원 추가 실패', error.message || FALLBACK_ERROR) }
  }
  async function changeRole(member, role) {
    const before = members
    setMembers(current => current.map(item => item.user_id === member.user_id ? { ...item, role } : item))
    try { await updateMember(project.id, member.user_id, role); notify('success', '권한 변경 완료', `${member.name}님의 권한을 ${role}로 변경했습니다.`) }
    catch (error) { setMembers(before); notify('error', '권한 변경 실패', error.message || FALLBACK_ERROR) }
  }
  async function kick(member) {
    const before = members; setMembers(current => current.filter(item => item.user_id !== member.user_id))
    try { await removeMember(project.id, member.user_id); notify('success', '팀원 제외 완료', `${member.name}님을 프로젝트에서 제외했습니다.`) }
    catch (error) { setMembers(before); notify('error', '팀원 제외 실패', error.message || FALLBACK_ERROR) }
  }
  async function upload(event) {
    const file = event.target.files?.[0]; if (!file) return
    try { const document = await uploadProjectDocument(project.id, file); setDocuments(current => [document, ...current]); notify('success', '문서 업로드 완료', `${document.filename} 처리가 완료되었습니다.`) }
    catch (error) { notify('error', '문서 업로드 실패', error.message || FALLBACK_ERROR) }
    finally { event.target.value = '' }
  }

  return <div className="app-frame"><header className="project-header"><button className="brand-button" onClick={onBack}><Logo/></button><span className="slash">/</span><strong>{project.name}</strong><span className="status-pill">진행 중</span><div className="header-spacer"/><div className="avatars">{members.slice(0, 3).map(member => <i key={member.id}>{member.name.slice(0, 1)}</i>)}</div><button className="primary" onClick={() => fileRef.current?.click()} disabled={project.role === 'VIEWER'}>문서 업로드</button><input ref={fileRef} hidden type="file" onChange={upload}/></header>
    <nav className="tabs">{[['dashboard','대시보드'],['documents','문서'],['board','보드'],['settings','설정']].map(([key,label]) => <button className={tab === key ? 'active' : ''} onClick={() => setTab(key)} key={key}>{label}</button>)}</nav>
    <main className="workspace-main">{loading ? <div className="empty-card">불러오는 중...</div> : tab === 'documents' ? <DocumentsView documents={documents} canEdit={project.role !== 'VIEWER'} onUpload={() => fileRef.current?.click()}/> : tab === 'settings' ? <MembersView members={members} role={project.role} onInvite={invite} onRole={changeRole} onRemove={kick}/> : tab === 'dashboard' ? <DashboardView documents={documents} members={members}/> : <BoardView/>}</main></div>
}

function DocumentsView({ documents, canEdit, onUpload }) {
  return <><section className="page-heading"><div><p className="eyebrow">PROJECT DOCUMENTS</p><h1>문서</h1><p>업로드된 문서와 처리 상태를 확인합니다.</p></div>{canEdit && <button className="primary" onClick={onUpload}>문서 업로드</button>}</section>
    <section className="panel table-panel"><div className="panel-head"><h2>전체 문서</h2><span>{documents.length}건</span></div>{documents.length ? <ul className="document-list">{documents.map(doc => <li key={doc.id}><span className="file-icon">{doc.file_type?.toUpperCase()}</span><div><strong>{doc.filename}</strong><small>{doc.extract_method || '처리 완료'} · {doc.char_count?.toLocaleString() || 0}자</small></div><span className="type-pill">{doc.document_type || '미분류'}</span><span className="complete-pill">{doc.status}</span><time>{new Date(doc.created_at).toLocaleDateString()}</time></li>)}</ul> : <EmptyDocuments onUpload={onUpload} canEdit={canEdit}/>}</section></>
}
function EmptyDocuments({ onUpload, canEdit }) { return <div className="drop-zone"><b>↑</b><h2>문서를 업로드해 시작하세요.</h2><p>PDF · DOCX · HWPX · JPG · PNG</p>{canEdit && <button onClick={onUpload}>파일 선택</button>}</div> }

function MembersView({ members, role, onInvite, onRole, onRemove }) {
  return <><section className="page-heading"><div><p className="eyebrow">PROJECT SETTINGS</p><h1>프로젝트 설정</h1><p>팀원과 접근 권한을 관리합니다.</p></div></section><section className="panel settings-panel"><div className="panel-head"><h2>팀원</h2><span>{members.length}명</span></div>
    {role === 'OWNER' && <form className="invite" onSubmit={onInvite}><input name="login_id" placeholder="팀원 아이디" required/><select name="role"><option>EDITOR</option><option>VIEWER</option></select><button className="primary">추가</button></form>}
    <ul className="member-list">{members.map(member => <li key={member.id}><i>{member.name.slice(0,1)}</i><div><strong>{member.name}</strong><small>@{member.login_id}</small></div>{role === 'OWNER' && member.role !== 'OWNER' ? <><select value={member.role} onChange={event => onRole(member, event.target.value)}><option>EDITOR</option><option>VIEWER</option></select><button onClick={() => onRemove(member)}>제외</button></> : <span className="type-pill">{member.role}</span>}</li>)}</ul></section></>
}

function DashboardView({ documents, members }) { return <><section className="page-heading"><div><p className="eyebrow">PROJECT OVERVIEW</p><h1>대시보드</h1><p>프로젝트 현황을 한눈에 확인합니다.</p></div></section><div className="stat-grid"><Stat label="전체 문서" value={documents.length}/><Stat label="처리 중" value={documents.filter(d => !['COMPLETED','EXTRACTED'].includes(d.status)).length}/><Stat label="팀원" value={members.length}/><Stat label="승인 대기" value="0" accent/></div><div className="dashboard-grid"><section className="panel"><div className="panel-head"><h2>최근 문서</h2></div><ul className="document-list compact-list">{documents.slice(0,5).map(doc => <li key={doc.id}><span className="file-icon">{doc.file_type?.toUpperCase()}</span><div><strong>{doc.filename}</strong><small>{doc.status}</small></div></li>)}</ul></section><section className="panel future-panel"><h2>이번 주 활동</h2><p>태스크와 활동 로그 기능이 연결되면 이곳에 프로젝트 활동이 표시됩니다.</p></section></div></> }
function Stat({ label, value, accent }) { return <section className="stat-card"><span>{label}</span><strong className={accent ? 'accent' : ''}>{value}</strong></section> }
function BoardView() { return <><section className="page-heading"><div><p className="eyebrow">TASK BOARD</p><h1>보드</h1><p>AI 제안을 승인하면 프로젝트 태스크로 등록됩니다.</p></div></section><div className="board"><BoardColumn title="TODO"/><BoardColumn title="DOING"/><BoardColumn title="DONE"/></div></> }
function BoardColumn({ title }) { return <section><div><strong>{title}</strong><span>0</span></div><p>태스크 기능 연결 후 표시됩니다.</p></section> }

export default function App() {
  const [user, setUser] = useState(null), [loading, setLoading] = useState(true), [projects, setProjects] = useState([]), [selected, setSelected] = useState(null), [toast, setToast] = useState(null)
  const toastTimer = useRef(null)
  const notify = useCallback((type, title, message) => { clearTimeout(toastTimer.current); setToast({ type, title, message }); toastTimer.current = setTimeout(() => setToast(null), 3500) }, [])
  useEffect(() => { const token = localStorage.getItem('tasqra_token'); if (token) getMe().then(account => { setUser(account); return listProjects() }).then(rows => rows && setProjects(rows)).catch(() => localStorage.removeItem('tasqra_token')).finally(() => setLoading(false)); else queueMicrotask(() => setLoading(false)); return () => clearTimeout(toastTimer.current) }, [])
  async function makeProject(event) { event.preventDefault(); const form = event.currentTarget; try { const project = await createProject(Object.fromEntries(new FormData(form))); setProjects(current => [project, ...current]); form.reset(); notify('success','프로젝트 생성 완료',`${project.name} 프로젝트를 만들었습니다.`); setSelected(project); return true } catch(error) { notify('error','프로젝트 생성 실패',error.message || FALLBACK_ERROR); return false } }
  function logout() { localStorage.removeItem('tasqra_token'); setUser(null); setProjects([]); setSelected(null) }
  if (loading) return <div className="center">Tasqra를 불러오는 중...</div>
  return <><Toast toast={toast} onClose={() => setToast(null)}/>{!user ? <AuthScreen onAuthenticated={async account => { setUser(account); setProjects(await listProjects()) }} notify={notify}/> : selected ? <Workspace project={selected} onBack={() => setSelected(null)} notify={notify}/> : <ProjectsScreen user={user} projects={projects} onCreate={makeProject} onSelect={setSelected} onLogout={logout}/>}</>
}

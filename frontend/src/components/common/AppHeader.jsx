import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useInvitationsQuery } from '../../hooks/useInvitationsQuery'
import Logo from './Logo'

export default function AppHeader({ user, onLogout, notify, project }) {
  const [open, setOpen] = useState(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const rootRef = useRef(null)
  const navigate = useNavigate()
  const invitationData = useInvitationsQuery(user?.id, notify)

  useEffect(() => {
    const close = event => {
      if (!rootRef.current?.contains(event.target)) {
        setOpen(null)
        setMobileOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  function logout() {
    onLogout?.()
    setOpen(null)
    setMobileOpen(false)
    navigate('/')
  }

  return <header className="app-header" ref={rootRef}>
    <Link className="app-header__brand" to={user ? '/projects' : '/'}><Logo/></Link>
    {project && <><span className="app-header__divider">/</span><strong className="app-header__project">{project.name}</strong></>}
    <button className="mobile-menu-button" aria-label="메뉴 열기" aria-expanded={mobileOpen} onClick={() => setMobileOpen(value => !value)}>☰</button>
    <nav className={`app-header__nav ${mobileOpen ? 'is-open' : ''}`}>
      {!user ? <><a href="/#features">기능 소개</a><Link to="/login">로그인</Link><Link className="primary" to="/signup">무료로 시작하기</Link></> : <>
        <Link to="/projects">내 프로젝트</Link>
        <div className="header-menu">
          <button className="header-icon-button" aria-label="알림" onClick={() => setOpen(open === 'notifications' ? null : 'notifications')}>🔔{invitationData.invitations.length > 0 && <b>{invitationData.invitations.length}</b>}</button>
          {open === 'notifications' && <NotificationPanel {...invitationData}/>} 
        </div>
        <div className="header-menu">
          <button className="profile-button" onClick={() => setOpen(open === 'profile' ? null : 'profile')}><i>{user.name.slice(0, 1)}</i><span>{user.name}</span></button>
          {open === 'profile' && <ProfilePanel user={user}/>} 
        </div>
        <button className="logout-button" onClick={logout}>로그아웃</button>
      </>}
    </nav>
  </header>
}

function NotificationPanel({ invitations, responding, accept, decline }) {
  return <section className="header-popover notification-panel"><h2>알림</h2>{invitations.length === 0 ? <p className="popover-empty">새로운 알림이 없습니다.</p> : invitations.map(item => <article key={item.id}><strong>{item.project_name}</strong><p>{item.inviter_name}님이 {item.role} 권한으로 초대했습니다.</p><div><button onClick={() => decline(item.id)} disabled={responding}>거절</button><button className="primary" onClick={() => accept(item.id)} disabled={responding}>수락</button></div></article>)}</section>
}

function ProfilePanel({ user }) {
  return <section className="header-popover profile-panel"><h2>마이페이지</h2><div className="profile-summary"><i>{user.name.slice(0, 1)}</i><div><strong>{user.name}</strong><span>@{user.login_id}</span></div></div><dl><dt>이메일</dt><dd>{user.email}</dd></dl></section>
}

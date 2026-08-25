import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useInvitationsQuery } from '../../hooks/useInvitationsQuery'
import Logo from './Logo'
import { applyThemeColor, DEFAULT_THEME_COLOR, getSavedThemeColor, hexToHsl, hslToHex, THEME_PRESETS } from '../../utils/theme'

export default function AppHeader({ user, onLogout, notify, project, section }) {
  const [open, setOpen] = useState(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [themeColor, setThemeColor] = useState(getSavedThemeColor)
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
    {project && <div className="app-header__context"><span>{project.name}</span>{section && <><i>/</i><strong>{section}</strong></>}</div>}
    <button className="mobile-menu-button" aria-label="메뉴 열기" aria-expanded={mobileOpen} onClick={() => setMobileOpen(value => !value)}>☰</button>
    <nav className={`app-header__nav ${mobileOpen ? 'is-open' : ''}`}>
      {!user ? <><a href="/#features">기능 소개</a><Link to="/login">로그인</Link><Link className="primary" to="/signup">무료로 시작하기</Link></> : <>
        <Link to="/projects">내 프로젝트</Link>
        <div className="header-menu theme-menu">
          <button className="theme-header-button" aria-label="화면 테마 선택" title="화면 테마" onClick={() => setOpen(open === 'theme' ? null : 'theme')}><i style={{ background: themeColor }}/></button>
          {open === 'theme' && <ThemePanel color={themeColor} onChange={color => setThemeColor(applyThemeColor(color))}/>}
        </div>
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

function ThemePanel({ color, onChange }) {
  const hsl = hexToHsl(color)
  const wheelRef = useRef(null)

  function chooseFromWheel(event) {
    const rect = wheelRef.current.getBoundingClientRect()
    const x = event.clientX - rect.left - rect.width / 2
    const y = event.clientY - rect.top - rect.height / 2
    const radius = rect.width / 2
    const saturation = Math.min(100, Math.round(Math.hypot(x, y) / radius * 100))
    const hue = Math.round((Math.atan2(y, x) * 180 / Math.PI + 90 + 360) % 360)
    onChange(hslToHex({ h: hue, s: saturation, l: hsl.l }))
  }

  function startWheel(event) {
    event.currentTarget.setPointerCapture(event.pointerId)
    chooseFromWheel(event)
  }

  const angle = (hsl.h - 90) * Math.PI / 180
  const distance = hsl.s * .72
  return <section className="header-popover theme-panel"><div className="theme-panel__head"><div><h2>화면 테마</h2><p>색상과 밝기를 선택하세요.</p></div><span style={{ background: color }}/></div><div ref={wheelRef} className="theme-color-wheel" onPointerDown={startWheel} onPointerMove={event => event.currentTarget.hasPointerCapture(event.pointerId) && chooseFromWheel(event)}><i style={{ transform:`translate(${Math.cos(angle) * distance}px,${Math.sin(angle) * distance}px)` }}/></div><label className="theme-lightness"><span>밝기</span><input type="range" min="0" max="100" value={hsl.l} onChange={event => onChange(hslToHex({ ...hsl, l:Number(event.target.value) }))}/></label><div className="theme-panel__presets">{THEME_PRESETS.map(preset => <button type="button" key={preset.color} className={color === preset.color ? 'is-active' : ''} onClick={() => onChange(preset.color)} title={preset.name} aria-label={`${preset.name} 테마`} style={{ background:preset.color }}/>)}</div><button type="button" className="theme-panel__reset" onClick={() => onChange(DEFAULT_THEME_COLOR)}>기본 네이비로 초기화</button></section>
}

function NotificationPanel({ invitations, responding, accept, decline }) {
  return <section className="header-popover notification-panel"><h2>알림</h2>{invitations.length === 0 ? <p className="popover-empty">새로운 알림이 없습니다.</p> : invitations.map(item => <article key={item.id}><strong>{item.project_name}</strong><p>{item.inviter_name}님이 {item.role} 권한으로 초대했습니다.</p><div><button onClick={() => decline(item.id)} disabled={responding}>거절</button><button className="primary" onClick={() => accept(item.id)} disabled={responding}>수락</button></div></article>)}</section>
}

function ProfilePanel({ user }) {
  return <section className="header-popover profile-panel"><h2>마이페이지</h2><div className="profile-summary"><i>{user.name.slice(0, 1)}</i><div><strong>{user.name}</strong><span>@{user.login_id}</span></div></div><dl><dt>이메일</dt><dd>{user.email}</dd></dl></section>
}

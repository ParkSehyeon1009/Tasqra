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
    {(project || section) && <nav className="app-header__context" aria-label="현재 위치"><Link to="/projects">워크스페이스</Link>{project && <><i aria-hidden="true">›</i><Link className="app-header__project-link" to={`/projects/${project.id}/dashboard`}>{project.name}</Link></>}<i aria-hidden="true">›</i><strong>{section || '대시보드'}</strong></nav>}
    <button className="mobile-menu-button" aria-label={mobileOpen ? '메뉴 닫기' : '메뉴 열기'} aria-expanded={mobileOpen} onClick={() => setMobileOpen(value => !value)}>{mobileOpen ? '×' : '☰'}</button>
    <nav className={`app-header__nav ${mobileOpen ? 'is-open' : ''}`} aria-label={user ? '사용자 메뉴' : '주요 메뉴'}>
      {!user ? <><a href="/#features">기능 소개</a><Link to="/login">로그인</Link><Link className="primary" to="/signup">무료로 시작하기</Link></> : <>
        <Link className="app-header__projects-link" to="/projects">내 프로젝트</Link>
        <div className="app-header__utility-group">
        <div className="header-menu theme-menu">
          <button className="theme-header-button" aria-label="화면 테마 선택" aria-controls="theme-panel" aria-expanded={open === 'theme'} title="화면 테마" onClick={() => setOpen(open === 'theme' ? null : 'theme')}><i style={{ background: themeColor }}/></button>
          {open === 'theme' && <ThemePanel color={themeColor} onChange={color => setThemeColor(applyThemeColor(color))}/>}
        </div>
        <div className="header-menu">
          <button className="header-icon-button" aria-label="알림" aria-controls="notification-panel" aria-expanded={open === 'notifications'} onClick={() => setOpen(open === 'notifications' ? null : 'notifications')}><HeaderIcon name="bell"/>{invitationData.invitations.length > 0 && <b>{invitationData.invitations.length}</b>}</button>
          {open === 'notifications' && <NotificationPanel {...invitationData}/>} 
        </div>
        </div>
        <span className="app-header__divider" aria-hidden="true"/>
        <div className="app-header__account-group">
        <div className="header-menu">
          <button className="profile-button" aria-controls="profile-panel" aria-expanded={open === 'profile'} onClick={() => setOpen(open === 'profile' ? null : 'profile')}><i>{user.name.slice(0, 1)}</i><span>{user.name}</span><HeaderIcon name="chevron"/></button>
          {open === 'profile' && <ProfilePanel user={user}/>} 
        </div>
        <button className="logout-button" onClick={logout}>로그아웃</button>
        </div>
      </>}
    </nav>
  </header>
}

function HeaderIcon({ name }) {
  const common = { width:18, height:18, viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', strokeWidth:1.8, 'aria-hidden':true }
  if (name === 'chevron') return <svg {...common} className="profile-chevron"><path d="m8 10 4 4 4-4"/></svg>
  return <svg {...common}><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></svg>
}

function ThemePanel({ color, onChange }) {
  const hsl = hexToHsl(color)
  const [wheelSelection, setWheelSelection] = useState(() => ({ h: hsl.h, s: hsl.s }))
  const wheelRef = useRef(null)

  function chooseFromWheel(event) {
    const rect = wheelRef.current.getBoundingClientRect()
    const x = event.clientX - rect.left - rect.width / 2
    const y = event.clientY - rect.top - rect.height / 2
    const radius = rect.width / 2
    const saturation = Math.min(100, Math.round(Math.hypot(x, y) / radius * 100))
    const hue = Math.round((Math.atan2(y, x) * 180 / Math.PI + 90 + 360) % 360)
    setWheelSelection({ h: hue, s: saturation })
    onChange(hslToHex({ h: hue, s: saturation, l: hsl.l }))
  }

  function startWheel(event) {
    event.currentTarget.setPointerCapture(event.pointerId)
    chooseFromWheel(event)
  }

  function choosePreset(presetColor) {
    const preset = hexToHsl(presetColor)
    setWheelSelection({ h: preset.h, s: preset.s })
    onChange(presetColor)
  }

  const angle = (wheelSelection.h - 90) * Math.PI / 180
  const distance = wheelSelection.s * .72
  const wheelShade = hsl.l < 50 ? (50 - hsl.l) / 50 : 0
  const wheelTint = hsl.l > 50 ? (hsl.l - 50) / 50 : 0
  return <section id="theme-panel" className="header-popover theme-panel" aria-labelledby="theme-panel-title"><div className="theme-panel__head"><div><h2 id="theme-panel-title">화면 테마</h2><p>색상과 밝기를 선택하세요.</p></div><span style={{ background: color }}/></div><div ref={wheelRef} className="theme-color-wheel" style={{ '--wheel-shade':wheelShade, '--wheel-tint':wheelTint }} onPointerDown={startWheel} onPointerMove={event => event.currentTarget.hasPointerCapture(event.pointerId) && chooseFromWheel(event)}><i style={{ transform:`translate(${Math.cos(angle) * distance}px,${Math.sin(angle) * distance}px)` }}/></div><label className="theme-lightness"><span>밝기</span><input type="range" min="0" max="100" value={hsl.l} onChange={event => onChange(hslToHex({ ...wheelSelection, l:Number(event.target.value) }))}/></label><div className="theme-panel__presets">{THEME_PRESETS.map(preset => <button type="button" key={preset.color} className={color === preset.color ? 'is-active' : ''} onClick={() => choosePreset(preset.color)} title={preset.name} aria-label={`${preset.name} 테마`} style={{ background:preset.color }}/>)}</div><button type="button" className="theme-panel__reset" onClick={() => choosePreset(DEFAULT_THEME_COLOR)}>기본 네이비로 초기화</button></section>
}

function NotificationPanel({ invitations, responding, accept, decline }) {
  return <section id="notification-panel" className="header-popover notification-panel" aria-labelledby="notification-panel-title"><h2 id="notification-panel-title">알림</h2>{invitations.length === 0 ? <p className="popover-empty">새로운 알림이 없습니다.</p> : invitations.map(item => <article key={item.id}><strong>{item.project_name}</strong><p>{item.inviter_name}님이 {item.role} 권한으로 초대했습니다.</p><div><button onClick={() => decline(item.id)} disabled={responding}>거절</button><button className="primary" onClick={() => accept(item.id)} disabled={responding}>수락</button></div></article>)}</section>
}

function ProfilePanel({ user }) {
  return <section id="profile-panel" className="header-popover profile-panel" aria-labelledby="profile-panel-title"><h2 id="profile-panel-title">마이페이지</h2><div className="profile-summary"><i>{user.name.slice(0, 1)}</i><div><strong>{user.name}</strong><span>@{user.login_id}</span></div></div><dl><dt>이메일</dt><dd>{user.email}</dd></dl></section>
}

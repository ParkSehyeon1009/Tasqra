import { useEffect, useRef, useState } from 'react'

export default function ProjectCreateModal({ open, recentInvitees, pending, onClose, onSubmit }) {
  const [invites, setInvites] = useState([])
  const [loginId, setLoginId] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [nameError, setNameError] = useState('')
  const dialogRef = useRef(null)
  const nameRef = useRef(null)
  const previousFocusRef = useRef(null)
  const onCloseRef = useRef(onClose)

  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    if (!open) return
    previousFocusRef.current = document.activeElement
    requestAnimationFrame(() => {
      setInvites([])
      setLoginId('')
      setName('')
      setDescription('')
      setNameError('')
      nameRef.current?.focus()
    })
    const handleKeyDown = event => {
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); requestAnimationFrame(() => previousFocusRef.current?.focus()); return }
      if (event.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])')
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  if (!open) return null

  function closeDialog() {
    onClose()
    requestAnimationFrame(() => previousFocusRef.current?.focus())
  }

  function addInvite(value = loginId) {
    const normalized = value.trim()
    if (!normalized || invites.some(item => item.login_id === normalized)) return
    setInvites(current => [...current, { login_id: normalized, role: 'EDITOR' }])
    setLoginId('')
  }

  function submit(event) {
    event.preventDefault()
    const normalizedName = name.trim()
    if (!normalizedName) { setNameError('프로젝트명을 입력해 주세요.'); nameRef.current?.focus(); return }
    const pendingLoginId = loginId.trim()
    const invitations = pendingLoginId && !invites.some(item => item.login_id === pendingLoginId) ? [...invites, { login_id: pendingLoginId, role: 'EDITOR' }] : invites
    onSubmit({ project: { name: normalizedName, description: description.trim() || null }, invitations })
  }

  return <div className='dialog-backdrop' onMouseDown={event => { if (event.target === event.currentTarget) closeDialog() }}>
    <form className='project-dialog' ref={dialogRef} onSubmit={submit} role='dialog' aria-modal='true' aria-labelledby='project-create-title'>
      <header><div><p className='eyebrow'>NEW PROJECT</p><h2 id='project-create-title'>새 프로젝트 만들기</h2></div><button type='button' className='dialog-close' onClick={closeDialog} aria-label='프로젝트 생성 창 닫기'>×</button></header>
      <div className='dialog-field'><label htmlFor='project-name'>프로젝트명 <span aria-hidden='true'>*</span></label><input id='project-name' ref={nameRef} name='name' value={name} onChange={event => { setName(event.target.value); if (nameError) setNameError('') }} aria-invalid={Boolean(nameError)} aria-describedby={nameError ? 'project-name-error' : undefined} maxLength='200' placeholder='예: 2026년 운영 보고서'/>{nameError && <p id='project-name-error' className='field-error' role='alert'>{nameError}</p>}</div>
      <div className='dialog-field'><label htmlFor='project-description'>설명 <small>선택</small></label><textarea id='project-description' name='description' value={description} onChange={event => setDescription(event.target.value)} rows='3' placeholder='프로젝트의 목적이나 공유할 맥락을 입력하세요.'/></div>
      <fieldset><legend>팀원 초대 <small>나중에 설정에서 추가할 수도 있습니다.</small></legend><div className='invite-entry'><label className='sr-only' htmlFor='invite-login-id'>초대할 사용자 아이디</label><input id='invite-login-id' value={loginId} onChange={event => setLoginId(event.target.value)} placeholder='초대할 사용자 아이디'/><button type='button' onClick={() => addInvite()}>추가</button></div>{recentInvitees.length > 0 && <div className='recent-invitees'><span>최근 초대한 사용자</span>{recentInvitees.map(item => <button type='button' key={item.login_id} onClick={() => addInvite(item.login_id)}>+ {item.name} (@{item.login_id})</button>)}</div>}<ul className='invite-drafts'>{invites.map((item, index) => <li key={item.login_id}><span>@{item.login_id}</span><label className='sr-only' htmlFor={'invite-role-' + index}>초대 권한</label><select id={'invite-role-' + index} value={item.role} onChange={event => setInvites(current => current.map((invite, i) => i === index ? { ...invite, role: event.target.value } : invite))}><option value='EDITOR'>편집자</option><option value='VIEWER'>뷰어</option></select><button type='button' onClick={() => setInvites(current => current.filter((_, i) => i !== index))} aria-label={item.login_id + ' 초대 삭제'}>삭제</button></li>)}</ul></fieldset>
      <footer><button type='button' onClick={closeDialog}>취소</button><button className='primary' disabled={pending}>{pending ? '생성 중...' : '프로젝트 만들기'}</button></footer>
    </form>
  </div>
}

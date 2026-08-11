import { useState } from 'react'

export default function ProjectCreateModal({ open, recentInvitees, pending, onClose, onSubmit }) {
  const [invites, setInvites] = useState([])
  const [loginId, setLoginId] = useState('')
  if (!open) return null

  function addInvite(value = loginId) {
    const normalized = value.trim()
    if (!normalized || invites.some(item => item.login_id === normalized)) return
    setInvites(current => [...current, { login_id: normalized, role: 'EDITOR' }])
    setLoginId('')
  }

  function submit(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    onSubmit({ project: { name: form.get('name'), description: form.get('description') || null }, invitations: invites })
  }

  return <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}><form className="project-dialog" onSubmit={submit} onMouseDown={event => event.stopPropagation()}>
    <header><div><p className="eyebrow">NEW PROJECT</p><h2>새 프로젝트 만들기</h2></div><button type="button" className="dialog-close" onClick={onClose}>×</button></header>
    <label>프로젝트명<input name="name" required autoFocus maxLength="200" placeholder="프로젝트명을 입력하세요"/></label>
    <label>설명<textarea name="description" rows="3" placeholder="프로젝트에 대한 간단한 설명 (선택)"/></label>
    <fieldset><legend>팀원 초대 <small>나중에 설정에서 추가할 수도 있습니다.</small></legend>
      <div className="invite-entry"><input value={loginId} onChange={event => setLoginId(event.target.value)} placeholder="초대할 사용자 아이디"/><button type="button" onClick={() => addInvite()}>추가</button></div>
      {recentInvitees.length > 0 && <div className="recent-invitees"><span>최근 초대한 사용자</span>{recentInvitees.map(item => <button type="button" key={item.login_id} onClick={() => addInvite(item.login_id)}>+ {item.name} (@{item.login_id})</button>)}</div>}
      <ul className="invite-drafts">{invites.map((item, index) => <li key={item.login_id}><span>@{item.login_id}</span><select value={item.role} onChange={event => setInvites(current => current.map((invite, i) => i === index ? { ...invite, role: event.target.value } : invite))}><option value="EDITOR">편집자</option><option value="VIEWER">뷰어</option></select><button type="button" onClick={() => setInvites(current => current.filter((_, i) => i !== index))}>삭제</button></li>)}</ul>
    </fieldset>
    <footer><button type="button" onClick={onClose}>취소</button><button className="primary" disabled={pending}>프로젝트 만들기</button></footer>
  </form></div>
}

import { useState } from 'react'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import PageHeading from '../../components/common/PageHeading'

export default function MembersView({ project, members, invitations, onUpdateProject, updatingProject, onInvite, onCancelInvitation, onRole, onRemove, onDeleteProject, deleting }) {
  const [removeTarget, setRemoveTarget] = useState(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const canEditProject = project.role !== 'VIEWER'
  const isOwner = project.role === 'OWNER'

  async function updateInfo(event) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    try { await onUpdateProject({ name: values.name, description: values.description || null, status: values.status }) } catch { /* 공통 토스트에서 처리 */ }
  }

  return <><PageHeading eyebrow="PROJECT SETTINGS" title="프로젝트 설정" description="프로젝트 정보, 팀원과 접근 권한을 관리합니다."/>
    <div className="settings-layout"><section className="panel settings-panel"><div className="panel-head"><h2>프로젝트 정보</h2><span>{project.role}</span></div><form className="project-info-form" onSubmit={updateInfo}><label>프로젝트명<input name="name" defaultValue={project.name} required disabled={!canEditProject}/></label><label>설명<textarea name="description" defaultValue={project.description ?? ''} rows="3" disabled={!canEditProject}/></label><label>프로젝트 상태<select name="status" defaultValue={project.status} disabled={!canEditProject}><option value="ACTIVE">진행 중</option><option value="ARCHIVED">보관됨</option></select></label>{canEditProject && <button className="primary" disabled={updatingProject}>변경사항 저장</button>}</form></section>
    <section className="panel settings-panel settings-section"><div className="panel-head"><h2>팀원</h2><span>{members.length}명</span></div>{isOwner && <InviteForm onSubmit={onInvite}/>}<MemberList members={members} role={project.role} onRole={onRole} onRemove={setRemoveTarget}/></section></div>
    {isOwner && <InvitationList invitations={invitations} onCancel={onCancelInvitation}/>}
    {isOwner && <section className="panel danger-zone"><div><h2>프로젝트 영구 삭제</h2><p>프로젝트와 모든 문서, 분석 결과, 멤버 및 초대 정보가 영구적으로 삭제됩니다.</p></div><button className="danger-button" onClick={() => setDeleteOpen(true)} disabled={deleting}>프로젝트 영구 삭제</button></section>}
    <ConfirmDialog open={Boolean(removeTarget)} title="팀원을 제외할까요?" message={removeTarget ? `${removeTarget.name}님은 더 이상 이 프로젝트에 접근할 수 없습니다.` : ''} confirmLabel="제외" danger onCancel={() => setRemoveTarget(null)} onConfirm={() => { onRemove(removeTarget); setRemoveTarget(null) }}/>
    <ConfirmDialog open={deleteOpen} title="이 프로젝트를 영구 삭제하시겠습니까?" message="이 작업은 되돌릴 수 없습니다. 프로젝트의 모든 문서, 추출 텍스트, 분석 결과, 멤버와 초대 정보 및 업로드 원본 파일이 영구 삭제됩니다." confirmLabel="영구 삭제" confirmationText={project.name} danger onCancel={() => setDeleteOpen(false)} onConfirm={() => { setDeleteOpen(false); onDeleteProject() }}/></>
}

function InviteForm({ onSubmit }) {
  return <form className="invite" onSubmit={onSubmit}><input name="login_id" placeholder="초대할 사용자 아이디" required/><select name="role"><option value="EDITOR">편집자</option><option value="VIEWER">뷰어</option></select><button className="primary">초대 보내기</button></form>
}

function MemberList({ members, role, onRole, onRemove }) {
  return <ul className="member-list">{members.map(member => <li key={member.id}><i>{member.name.slice(0,1)}</i><div><strong>{member.name}</strong><small>@{member.login_id}</small></div>{role === 'OWNER' && member.role !== 'OWNER' ? <><select value={member.role} onChange={event => onRole(member, event.target.value)}><option value="EDITOR">편집자</option><option value="VIEWER">뷰어</option></select><button onClick={() => onRemove(member)}>제외</button></> : <span className="type-pill">{member.role}</span>}</li>)}</ul>
}

function InvitationList({ invitations, onCancel }) {
  return <section className="panel settings-panel settings-section"><div className="panel-head"><h2>초대 내역</h2><span>{invitations.filter(item => item.status === 'PENDING').length}건 대기</span></div>{invitations.length === 0 ? <p className="settings-empty">보낸 초대가 없습니다.</p> : <ul className="invitation-list">{invitations.map(invitation => <li key={invitation.id}><div><strong>{invitation.invitee_name}</strong><small>@{invitation.invitee_login_id} · {invitation.role}</small></div><span className={`invitation-status invitation-status--${invitation.status.toLowerCase()}`}>{statusLabel(invitation.status)}</span>{invitation.status === 'PENDING' && <button onClick={() => onCancel(invitation)}>초대 취소</button>}</li>)}</ul>}</section>
}

function statusLabel(status) {
  return { PENDING: '대기 중', ACCEPTED: '수락', DECLINED: '거절', CANCELED: '취소' }[status] ?? status
}

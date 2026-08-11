import { useState } from 'react'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import PageHeading from '../../components/common/PageHeading'

export default function MembersView({ projectName, members, role, onInvite, onRole, onRemove, onDeleteProject, deleting }) {
  const [removeTarget, setRemoveTarget] = useState(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  return <><PageHeading eyebrow="PROJECT SETTINGS" title="프로젝트 설정" description="팀원과 접근 권한을 관리합니다."/><section className="panel settings-panel"><div className="panel-head"><h2>팀원</h2><span>{members.length}명</span></div>
    {role === 'OWNER' && <InviteForm onSubmit={onInvite}/>}<MemberList members={members} role={role} onRole={onRole} onRemove={setRemoveTarget}/></section>
    {role === 'OWNER' && <section className="panel danger-zone"><div><h2>프로젝트 영구 삭제</h2><p>프로젝트와 모든 문서, 분석 결과, 멤버 및 초대 정보가 영구적으로 삭제됩니다.</p></div><button className="danger-button" onClick={() => setDeleteOpen(true)} disabled={deleting}>프로젝트 영구 삭제</button></section>}
    <ConfirmDialog open={Boolean(removeTarget)} title="팀원을 제외할까요?" message={removeTarget ? `${removeTarget.name}님은 더 이상 이 프로젝트에 접근할 수 없습니다.` : ''} confirmLabel="제외" danger onCancel={() => setRemoveTarget(null)} onConfirm={() => { onRemove(removeTarget); setRemoveTarget(null) }}/>
    <ConfirmDialog open={deleteOpen} title="이 프로젝트를 영구 삭제하시겠습니까?" message="이 작업은 되돌릴 수 없습니다. 프로젝트의 모든 문서, 추출 텍스트, 분석 결과, 멤버와 초대 정보 및 업로드 원본 파일이 영구 삭제됩니다." confirmLabel="영구 삭제" confirmationText={projectName} danger onCancel={() => setDeleteOpen(false)} onConfirm={() => { setDeleteOpen(false); onDeleteProject() }}/></>
}

function InviteForm({ onSubmit }) {
  return <form className="invite" onSubmit={onSubmit}><input name="login_id" placeholder="초대할 사용자 아이디" required/><select name="role"><option value="EDITOR">편집자</option><option value="VIEWER">뷰어</option></select><button className="primary">초대 보내기</button></form>
}

function MemberList({ members, role, onRole, onRemove }) {
  return <ul className="member-list">{members.map(member => <li key={member.id}><i>{member.name.slice(0,1)}</i><div><strong>{member.name}</strong><small>@{member.login_id}</small></div>{role === 'OWNER' && member.role !== 'OWNER' ? <><select value={member.role} onChange={event => onRole(member, event.target.value)}><option value="EDITOR">편집자</option><option value="VIEWER">뷰어</option></select><button onClick={() => onRemove(member)}>제외</button></> : <span className="type-pill">{member.role}</span>}</li>)}</ul>
}

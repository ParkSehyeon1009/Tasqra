import PageHeading from '../../components/common/PageHeading'

export default function MembersView({ members, role, onInvite, onRole, onRemove }) {
  return <><PageHeading eyebrow="PROJECT SETTINGS" title="프로젝트 설정" description="팀원과 접근 권한을 관리합니다."/><section className="panel settings-panel"><div className="panel-head"><h2>팀원</h2><span>{members.length}명</span></div>
    {role === 'OWNER' && <InviteForm onSubmit={onInvite}/>}<MemberList members={members} role={role} onRole={onRole} onRemove={onRemove}/></section></>
}

function InviteForm({ onSubmit }) {
  return <form className="invite" onSubmit={onSubmit}><input name="login_id" placeholder="팀원 아이디" required/><select name="role"><option>EDITOR</option><option>VIEWER</option></select><button className="primary">추가</button></form>
}

function MemberList({ members, role, onRole, onRemove }) {
  return <ul className="member-list">{members.map(member => <li key={member.id}><i>{member.name.slice(0,1)}</i><div><strong>{member.name}</strong><small>@{member.login_id}</small></div>{role === 'OWNER' && member.role !== 'OWNER' ? <><select value={member.role} onChange={event => onRole(member, event.target.value)}><option>EDITOR</option><option>VIEWER</option></select><button onClick={() => onRemove(member)}>제외</button></> : <span className="type-pill">{member.role}</span>}</li>)}</ul>
}

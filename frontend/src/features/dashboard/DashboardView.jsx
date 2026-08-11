import PageHeading from '../../components/common/PageHeading'

export default function DashboardView({ documents, members }) {
  const processingCount = documents.filter(document => !['COMPLETED','EXTRACTED'].includes(document.status)).length
  return <><PageHeading eyebrow="PROJECT OVERVIEW" title="대시보드" description="프로젝트 현황을 한눈에 확인합니다."/><div className="stat-grid"><Stat label="전체 문서" value={documents.length}/><Stat label="처리 중" value={processingCount}/><Stat label="팀원" value={members.length}/><Stat label="승인 대기" value="0" accent/></div><div className="dashboard-grid"><RecentDocuments documents={documents}/><section className="panel future-panel"><h2>이번 주 활동</h2><p>태스크와 활동 로그 기능이 연결되면 이곳에 프로젝트 활동이 표시됩니다.</p></section></div></>
}

function Stat({ label, value, accent }) {
  return <section className="stat-card"><span>{label}</span><strong className={accent ? 'accent' : ''}>{value}</strong></section>
}

function RecentDocuments({ documents }) {
  return <section className="panel"><div className="panel-head"><h2>최근 문서</h2></div><ul className="document-list compact-list">{documents.slice(0,5).map(document => <li key={document.id}><span className="file-icon">{document.file_type?.toUpperCase()}</span><div><strong>{document.filename}</strong><small>{document.status}</small></div></li>)}</ul></section>
}

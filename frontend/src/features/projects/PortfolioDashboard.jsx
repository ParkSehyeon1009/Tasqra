// =============================================================================
// 이 파일의 책임: 로그인 직후 모든 참여 프로젝트의 실제 현황을 한 화면에 모은다.
// 다른 파일과의 관계: portfolio dashboard API를 한 번 조회해 기존 프로젝트 목록과
//   결합하고, 각 프로젝트 작업공간 경로로 이동한다.
// Spring 비교: 여러 프로젝트의 읽기 모델을 소비하는 전용 Dashboard View다.
// =============================================================================

import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getPortfolioDashboard } from '../../api/dashboard'
import { formatNumber } from '../../utils/format'
import { projectColorIndex } from '../../utils/projectColor'
import './PortfolioDashboard.css'

const ACTIVITY_LABELS = {
  CREATED: '태스크 생성',
  UPDATED: '태스크 수정',
  STATUS_CHANGED: '상태 변경',
  DELETED: '태스크 삭제',
  AUTO_NOTE: '자동 메모',
}

export default function PortfolioDashboard({ user, projects, invitations, onCreate }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('ACTIVE')
  const portfolioQuery = useQuery({
    queryKey: ['portfolio-dashboard', user.id],
    queryFn: () => getPortfolioDashboard({ recentDocumentLimit: 5, activityLimit: 20 }),
    staleTime: 0,
    refetchOnMount: 'always',
  })
  const dashboardByProject = useMemo(
    () => new Map((portfolioQuery.data?.projects ?? []).map(item => [Number(item.project_id), item.dashboard])),
    [portfolioQuery.data],
  )
  const rows = projects.map(project => ({
    project,
    dashboard: dashboardByProject.get(Number(project.id)),
  }))
  const summary = rows.reduce((total, row) => {
    const data = row.dashboard
    total.documents += data?.documents?.total ?? 0
    total.openTasks += data?.open_tasks ?? 0
    total.failed += data?.documents?.failed ?? 0
    total.review += data?.review_pending ?? 0
    total.amounts += data?.pending_amount_items ?? 0
    total.completed += data?.documents?.completed ?? 0
    total.extracted += data?.documents?.extracted ?? 0
    total.processing += data?.documents?.processing ?? 0
    return total
  }, { documents:0, openTasks:0, failed:0, review:0, amounts:0, completed:0, extracted:0, processing:0 })

  const statusCounts = projects.reduce((counts, project) => {
    const status = project.status === 'ARCHIVED' ? 'ARCHIVED' : 'ACTIVE'
    counts[status] += 1
    return counts
  }, { ACTIVE: 0, ARCHIVED: 0 })
  const filteredRows = rows.filter(({ project }) => {
    const matchesStatus = (project.status === 'ARCHIVED' ? 'ARCHIVED' : 'ACTIVE') === statusFilter
    const matchesQuery = project.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
    return matchesStatus && matchesQuery
  })
  const recentWork = useMemo(() => buildRecentWork(projects, portfolioQuery.data), [projects, portfolioQuery.data])
  const waitingTotal = summary.review + summary.amounts + summary.failed + invitations.length
  const loading = portfolioQuery.isPending
  const today = new Intl.DateTimeFormat('ko-KR', { month:'long', day:'numeric', weekday:'long' }).format(new Date())

  return <main className="portfolio-main">
    <section className="portfolio-welcome">
      <div><p className="eyebrow">WORKSPACE OVERVIEW</p><h1>{user.name}님, 좋은 하루예요.</h1><p>{today} · 전체 프로젝트 현황과 지금 확인할 일을 한눈에 살펴보세요.</p></div>
      <button className="primary portfolio-create" onClick={onCreate}>＋ 새 프로젝트</button>
    </section>

    {portfolioQuery.isError && <div className="portfolio-data-notice">전체 프로젝트 현황을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div>}

    <section className="portfolio-stat-grid" aria-label="전체 프로젝트 요약">
      <StatCard icon="folder" label="전체 프로젝트" value={projects.length} note="참여 중인 프로젝트"/>
      <StatCard icon="document" label="등록 문서" value={loading ? null : summary.documents} note="전체 프로젝트 합계"/>
      <StatCard icon="task" label="열린 태스크" value={loading ? null : summary.openTasks} note="완료 전 태스크"/>
      <StatCard icon="alert" label="확인 필요" value={loading ? null : waitingTotal} note="검수·승인·실패·초대" tone={waitingTotal ? 'danger' : ''}/>
    </section>

    <div className="portfolio-layout">
      <section className="portfolio-projects panel">
        <header className="portfolio-panel-head"><div><h2>내 프로젝트</h2><p>프로젝트를 선택하면 기존 작업 공간으로 이동합니다.</p></div><span>{filteredRows.length}개</span></header>
        <div className="portfolio-project-tools">
          <label><span className="sr-only">프로젝트 검색</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="프로젝트 검색"/></label>
          <div className="portfolio-filter-tabs" role="group" aria-label="프로젝트 상태">
            <button type="button" className="status-active" aria-pressed={statusFilter === 'ACTIVE'} onClick={() => setStatusFilter('ACTIVE')}>진행 중 {statusCounts.ACTIVE}</button>
            <button type="button" className="status-archived" aria-pressed={statusFilter === 'ARCHIVED'} onClick={() => setStatusFilter('ARCHIVED')}>보관됨 {statusCounts.ARCHIVED}</button>
          </div>
        </div>
        <div className="portfolio-project-list">{filteredRows.map(({ project, dashboard }) => <ProjectRow key={project.id} project={project} dashboard={dashboard} marker={projectColorIndex(project.id)} onOpen={() => navigate(`/projects/${project.id}/dashboard`)}/>)}</div>
        {filteredRows.length === 0 && <div className="portfolio-empty">검색 조건에 맞는 프로젝트가 없습니다.</div>}
        <button className="portfolio-new-row" onClick={onCreate}>＋ 새 프로젝트 만들기</button>
      </section>

      <aside className="portfolio-side">
        <AttentionCard invitations={invitations} onOpen={(projectId, tab, queryString='') => navigate(`/projects/${projectId}/${tab}${queryString}`)} rows={rows}/>
        <RecentWork items={recentWork} onOpen={navigate}/>
        <QuickStart projects={projects} onCreate={onCreate} onOpen={navigate}/>
        <ProcessingChart summary={summary}/>
      </aside>
    </div>
  </main>
}

function StatCard({ icon, label, value, note, tone='' }) {
  return <article className={`portfolio-stat-card ${tone ? `is-${tone}` : ''}`}><Icon name={icon}/><div><span>{label}</span><strong>{value === null ? '—' : formatNumber(value)}</strong><small>{note}</small></div></article>
}

function ProjectRow({ project, dashboard, marker, onOpen }) {
  const documents = dashboard?.documents
  const extractionCompleted = (documents?.completed ?? 0) + (documents?.extracted ?? 0)
  const completion = documents?.total ? Math.round((extractionCompleted / documents.total) * 100) : 0
  return <button className="portfolio-project-row" onClick={onOpen}>
    <span className={`portfolio-project-mark marker-${marker}`}><Icon name="folder"/></span>
    <span className="portfolio-project-name"><strong>{project.name}</strong><small className={`status-${project.status?.toLowerCase()}`}><i/>{projectStatus(project.status)}</small></span>
    <span className="portfolio-progress"><small>문서 처리율 <b>{dashboard ? `${completion}%` : '—'}</b></small><i><b style={{ width:`${completion}%` }}/></i></span>
    <span className="portfolio-project-metric"><small>문서</small><strong>{dashboard ? formatNumber(documents?.total ?? 0) : '—'}</strong></span>
    <span className="portfolio-project-metric"><small>열린 태스크</small><strong>{dashboard ? formatNumber(dashboard.open_tasks ?? 0) : '—'}</strong></span>
    <span className={`portfolio-project-metric ${(dashboard?.documents?.failed ?? 0) > 0 ? 'is-danger' : ''}`}><small>처리 실패</small><strong>{dashboard ? formatNumber(documents?.failed ?? 0) : '—'}</strong></span>
    <span className="portfolio-project-role"><small>역할</small><strong>{roleLabel(project.role)}</strong></span>
    <span className="portfolio-open">›</span>
  </button>
}

function AttentionCard({ invitations, rows, onOpen }) {
  const definitions = [
    ['OCR 검수', data => data?.review_pending ?? 0, 'documents', '?document_state=REVIEW_REQUIRED'],
    ['금액 승인', data => data?.pending_amount_items ?? 0, 'amounts', ''],
    ['처리 실패', data => data?.documents?.failed ?? 0, 'documents', '?document_state=FAILED'],
  ]
  const items = rows.flatMap(({ project, dashboard }) => definitions
    .map(([label, countOf, tab, query]) => ({ project, label, count:countOf(dashboard), tab, query }))
    .filter(item => item.count > 0))
    .sort((a,b) => b.count - a.count || a.project.name.localeCompare(b.project.name, 'ko'))

  return <section className="portfolio-attention panel">
    <header className="portfolio-panel-head"><div><h2>지금 확인할 일</h2><p>프로젝트별 항목을 선택해 바로 확인하세요.</p></div></header>
    {items.length ? <div className="portfolio-attention-list">{items.map(item => <button key={`${item.project.id}-${item.label}`} onClick={() => onOpen(item.project.id,item.tab,item.query)}><span><b>{item.project.name}</b><small>{item.label}</small></span><strong>{formatNumber(item.count)}건</strong><i>›</i></button>)}</div> : <div className="portfolio-attention-empty">현재 확인할 항목이 없습니다.</div>}
    {invitations.length > 0 && <p className="portfolio-invite-note">새 프로젝트 초대 {invitations.length}건은 상단 알림에서 확인할 수 있습니다.</p>}
  </section>
}

function RecentWork({ items, onOpen }) {
  return <section className="portfolio-recent panel"><header className="portfolio-panel-head"><div><h2>최근 작업</h2><p>전체 프로젝트의 최근 문서와 태스크 활동입니다.</p></div></header>{items.length ? <ul>{items.slice(0,5).map(item => <li key={item.key}><button onClick={() => onOpen(item.path)}><Icon name={item.kind === 'document' ? 'document' : 'task'}/><span><strong>{item.title}</strong><small><b className="portfolio-recent-project-name">{item.projectName}</b> · {item.description}</small></span><time>{relativeDate(item.createdAt)}</time></button></li>)}</ul> : <div className="portfolio-empty">아직 최근 작업이 없습니다.</div>}</section>
}

function QuickStart({ projects, onCreate, onOpen }) {
  const first = projects[0]
  return <section className="portfolio-quick panel"><header className="portfolio-panel-head"><div><h2>빠른 시작</h2></div></header><div><button disabled={!first} onClick={() => first && onOpen(`/projects/${first.id}/documents`)}><Icon name="upload"/>문서 업로드</button><button onClick={onCreate}><Icon name="folder"/>프로젝트</button><button disabled={!first} onClick={() => first && onOpen(`/projects/${first.id}/board`)}><Icon name="task"/>보드 열기</button></div></section>
}

function ProcessingChart({ summary }) {
  const extractionCompleted = summary.completed + summary.extracted
  const known = extractionCompleted + summary.processing + summary.failed
  const waiting = Math.max(0, summary.documents - known)
  const values = [extractionCompleted, summary.processing, summary.failed, waiting]
  let cursor = 0
  const stops = summary.documents > 0
    ? values.map((value,index) => { const start=cursor; cursor += value / summary.documents * 100; return `var(--chart-${index}) ${start}% ${cursor}%` }).join(',')
    : ''
  const background = summary.documents > 0 ? `conic-gradient(${stops})` : 'var(--c-border)'
  const chartRows = [['추출 완료',extractionCompleted],['처리 중',summary.processing],['처리 실패',summary.failed],['대기·기타',waiting]]
  return <section className="portfolio-chart panel"><header className="portfolio-panel-head"><div><h2>문서 처리 현황</h2><p>전체 프로젝트의 현재 처리 단계입니다.</p></div></header><div className="portfolio-chart__body"><div className={`portfolio-donut ${summary.documents ? '' : 'is-empty'}`} style={{ background }}><span><strong>{formatNumber(summary.documents)}</strong><small>전체 문서</small></span></div><ul>{chartRows.map(([label,value],index) => <li key={label}><i className={`chart-${index}`}/><span>{label}</span><strong>{formatNumber(value)}</strong></li>)}</ul></div></section>
}

function buildRecentWork(projects, portfolio) {
  const items = []
  const projectById = new Map(projects.map(project => [Number(project.id), project]))
  ;(portfolio?.projects ?? []).forEach(item => {
    const project = projectById.get(Number(item.project_id))
    if (!project) return
    ;(item.dashboard?.recent_documents ?? []).forEach(document => items.push({ key:`document-${project.id}-${document.id}`,kind:'document',title:document.filename,projectName:project.name,description:'문서 업로드',createdAt:document.created_at,path:`/projects/${project.id}/documents/${document.id}` }))
  })
  ;(portfolio?.recent_task_activity ?? []).forEach(activity => {
    const project = projectById.get(Number(activity.project_id))
    if (!project) return
    items.push({ key:`activity-${project.id}-${activity.id}`,kind:'task',title:activity.task_title || '태스크',projectName:project.name,description:ACTIVITY_LABELS[activity.event_type] ?? activity.event_type,createdAt:activity.created_at,path:`/projects/${project.id}/board${activity.task_id ? `?task_id=${activity.task_id}` : ''}` })
  })
  return items.filter(item => item.createdAt).sort((a,b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0,12)
}

function relativeDate(value) {
  const diff = Date.now() - new Date(value).getTime()
  if (diff < 60_000) return '방금'
  if (diff < 3_600_000) return `${Math.max(1,Math.floor(diff/60_000))}분 전`
  if (diff < 86_400_000) return `${Math.floor(diff/3_600_000)}시간 전`
  if (diff < 604_800_000) return `${Math.floor(diff/86_400_000)}일 전`
  return new Intl.DateTimeFormat('ko-KR',{month:'numeric',day:'numeric'}).format(new Date(value))
}
function projectStatus(status){ return status === 'ARCHIVED' ? '보관됨' : status === 'COMPLETED' ? '완료' : '진행 중' }
function roleLabel(role){ return role === 'OWNER' ? '소유자' : role === 'EDITOR' ? '편집자' : '뷰어' }

function Icon({ name }) {
  const common={viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:'1.8','aria-hidden':true}
  if(name==='folder') return <svg {...common}><path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>
  if(name==='document') return <svg {...common}><path d="M6 3h8l4 4v14H6zM14 3v5h5M9 12h6M9 16h6"/></svg>
  if(name==='task') return <svg {...common}><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></svg>
  if(name==='alert') return <svg {...common}><path d="M10.3 4.2 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0ZM12 9v4M12 17h.01"/></svg>
  return <svg {...common}><path d="M12 16V4m0 0L7 9m5-5 5 5M4 15v5h16v-5"/></svg>
}

// =============================================================================
// 이 파일의 책임: 프로젝트 핵심 현황 화면이다(DSH-001). 지표 카드 · 문서 유형
//   분포 · OCR 검수 필요 목록 · 최근 문서를 보여주고, 각 항목에서 관련 화면으로
//   이동시킨다.
// 다른 파일과의 관계: api/dashboard.js 로 집계를 받는다. OCR 검수 목록 항목만
//   상위(WorkspacePage → useWorkspaceData)가 넘겨준 documents 를 쓴다.
//   표기는 utils/documentStatus.js · utils/documentType.js 를 쓴다.
// Spring 비교: 서버가 만든 뷰 모델을 그대로 그리는 화면이다. 숫자를 화면에서
//   다시 계산하지 않는다.
//
// 숫자를 화면에서 세지 않게 바꾼 이유
//   전에는 documents 배열을 filter().length 로 세었다. 그런데 그 배열은
//   GET /documents 첫 페이지이고 기본 size 가 20 이다(useWorkspaceData 가
//   응답의 items 만 쓴다). 문서가 21건 이상이면 카드 숫자가 조용히 틀렸다 —
//   에러도 안 나고 화면도 정상으로 보인다. 그래서 지표는 전부 서버 집계를 쓴다.
//
//   documents 를 아직 쓰는 곳이 하나 남아 있다 — "OCR 확인 필요" 목록의 항목들.
//   그 목록은 서버 집계에 포함하지 않았다. 대신 **건수는 서버 값(review_pending)
//   을 쓴다.** 그래서 문서가 많을 때 "3건 표시 · 외 N건" 의 N 이 맞다.
// =============================================================================

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getDashboard } from '../../api/dashboard'
import { listTasks } from '../../api/task'
import PageHeading from '../../components/common/PageHeading'
import { getDocumentStatus, getReviewStatus } from '../../utils/documentStatus'
import { getDocumentTypeLabel, isSupportedDocumentTypeFilter, UNCLASSIFIED_DOCUMENT_TYPE } from '../../utils/documentType'
import { formatDateShort, formatNumber } from '../../utils/format'
import ActionTaskPanel from './ActionTaskPanel'

export default function DashboardView({ projectId, documents, members }) {
  const navigate = useNavigate()
  const dashboardQuery = useQuery({
    queryKey: ['projects', projectId, 'dashboard'],
    queryFn: () => getDashboard(projectId),
    // 처리 중인 문서가 있으면 3초마다 다시 받는다. DSH-001 완료 판정이 "최신
    // 데이터가 지표·목록에 반영되고" 이므로, 추출이 끝나면 새로고침 없이 숫자가
    // 바뀌어야 한다. 처리 중이 0이면 폴링하지 않는다 — 가만히 있는 화면에
    // 요청을 계속 보낼 이유가 없다. useWorkspaceData 의 문서 목록 폴링과 같은
    // 간격이라 두 값이 크게 어긋나지 않는다.
    refetchInterval: query => (query.state.data?.documents?.processing > 0 ? 3_000 : false),
  })
  const tasksQuery = useQuery({
    queryKey: ['projects', projectId, 'tasks'],
    queryFn: () => listTasks(projectId),
  })
  const data = dashboardQuery.data
  const counts = data?.documents
  const goDocuments = () => navigate(`/projects/${projectId}/documents`)
  const goDocumentsByType = documentType => {
    const filter = documentType ?? UNCLASSIFIED_DOCUMENT_TYPE
    if (!isSupportedDocumentTypeFilter(filter)) return
    navigate(`/projects/${projectId}/documents?document_type=${encodeURIComponent(filter)}`)
  }

  // 서버 건수를 우선 쓰고, 아직 안 왔으면 넘겨받은 목록으로 임시 표시한다.
  const needsReview = documents.filter(document => ['PENDING', 'IN_PROGRESS'].includes(document.review_status))
  const reviewPending = data ? data.review_pending : needsReview.length
  const attentionTasks = (tasksQuery.data ?? []).filter(task => task.status !== 'DONE' && isDueSoon(task.due_on)).length
  const attentionTotal = (counts?.failed ?? 0) + (reviewPending ?? 0) + (data?.pending_amount_items ?? 0) + attentionTasks

  return <>
    <PageHeading eyebrow='PROJECT OVERVIEW' title='대시보드' description='지금 확인할 문서와 우선 처리할 액션 태스크를 확인하세요.'/>

    {dashboardQuery.isError && <section className='panel dashboard-notice'>
      <div><strong>현황 지표를 불러오지 못했습니다.</strong><p>{dashboardQuery.error?.message}</p></div>
      <button onClick={() => dashboardQuery.refetch()}>다시 시도</button>
    </section>}

    <section className='dashboard-summary-grid dashboard-summary-grid--compact' aria-label='프로젝트 핵심 현황'>
      <SummaryCard label='전체 문서' value={counts?.total} onOpen={goDocuments}/>
      <SummaryCard label='처리 중' value={counts?.processing} onOpen={goDocuments}/>
      <SummaryCard label='처리 완료' value={counts?.completed} onOpen={goDocuments}/>
      <SummaryCard label='처리 실패' value={counts?.failed} emphasis={counts?.failed > 0} onOpen={goDocuments}/>
      <SummaryCard label='열린 태스크' value={data?.open_tasks} onOpen={() => navigate(`/projects/${projectId}/board`)}/>
    </section>

    <div className="dashboard-top-grid">
      <section className='panel dashboard-next-actions'>
        <div className='panel-head'><div><h2>확인이 필요한 일</h2><p>사람이 확인해야 다음 단계로 넘어가는 항목입니다.</p></div><span>{formatNumber(attentionTotal)}건</span></div>
        <div className='dashboard-attention-summary'>
          <AttentionRow kind='문서' title='처리 실패' description='원인을 확인하고 문서를 다시 처리합니다.' count={counts?.failed} urgent onOpen={goDocuments}/>
          <AttentionRow kind='문서' title='OCR 검수' description='검수 후 최종 본문에 반영됩니다.' count={reviewPending} onOpen={goDocuments}/>
          <AttentionRow kind='금액' title='승인 대기' description='승인 전에는 산출물에 반영되지 않습니다.' count={data?.pending_amount_items}/>
          <AttentionRow kind='태스크' title='마감 임박' description='7일 이내 마감되는 열린 태스크입니다.' count={attentionTasks} onOpen={() => navigate(`/projects/${projectId}/board`)}/>
        </div>
        <div className="dashboard-panel-footer"><span>참여자 {formatNumber(members.length)}명</span><button onClick={goDocuments}>전체 문서 보기 →</button></div>
      </section>
      <ActionTaskPanel tasks={tasksQuery.data ?? []} loading={tasksQuery.isPending} onOpenBoard={() => navigate(`/projects/${projectId}/board`)}/>
    </div>

    <div className='dashboard-distribution-grid'><DocumentTypePanel types={data?.document_types} total={counts?.total} loaded={Boolean(data)} onOpenType={goDocumentsByType}/><ProcessingStatusPanel counts={counts} loaded={Boolean(data)} onOpen={goDocuments}/></div>

    <section className='panel dashboard-recent-panel'>
      <div className='panel-head'><div><h2>최근 문서</h2><p>최근에 업로드된 문서의 현재 상태입니다.</p></div><span>{formatNumber(counts?.total ?? null)}건</span></div>
      {data?.recent_documents?.length
        ? <ul className='dashboard-document-list dashboard-recent-list'>{data.recent_documents.map(document => <RecentDocument document={document} key={document.id} onOpen={() => navigate(`/projects/${projectId}/documents/${document.id}`)}/>)}</ul>
        : <div className='dashboard-empty-state'><strong>{data ? '등록된 문서가 없습니다.' : '문서 현황을 불러오는 중입니다.'}</strong><p>문서 탭에서 파일을 업로드하면 처리 현황이 표시됩니다.</p></div>}
      {counts?.total > (data?.recent_documents?.length ?? 0) && <div className="dashboard-panel-footer"><span>외 {formatNumber(counts.total - data.recent_documents.length)}건이 더 있습니다.</span><button onClick={goDocuments}>전체 문서 보기 →</button></div>}
    </section>
  </>
}

function AttentionRow({ kind, title, description, count, urgent = false, onOpen }) {
  const content = <><span className={urgent && count > 0 ? 'is-urgent' : ''}>{kind}</span><div><strong>{title}</strong><small>{description}</small></div><b>{formatNumber(count ?? null)}건</b>{onOpen && <em>→</em>}</>
  return onOpen ? <button onClick={onOpen}>{content}</button> : <div>{content}</div>
}

function ProcessingStatusPanel({ counts, loaded, onOpen }) {
  const total = counts?.total ?? 0
  const rows = [['처리 완료',counts?.completed,'success'],['텍스트 추출 완료',counts?.extracted,'ready'],['처리 중',counts?.processing,'progress'],['처리 실패',counts?.failed,'danger']]
  return <section className='panel dashboard-status-panel'><div className='panel-head'><div><h2>처리 상태</h2><p>전체 문서의 처리 단계별 비율입니다.</p></div><span>{formatNumber(counts?.total ?? null)}건</span></div>{loaded ? <div className='dashboard-status-list'>{rows.map(([label,value,tone]) => <button onClick={onOpen} key={label}><span>{label}</span><i><b className={`is-${tone}`} style={{ width:`${total ? (value / total) * 100 : 0}%` }}/></i><strong>{formatNumber(value)}건 · {total ? Math.round((value / total) * 100) : 0}%</strong></button>)}</div> : <div className='dashboard-empty-state'><strong>처리 상태를 불러오는 중입니다.</strong></div>}</section>
}

function isDueSoon(dueOn) {
  if (!dueOn) return false
  const due = new Date(`${dueOn}T23:59:59`)
  const now = new Date()
  return due >= now && due.getTime() - now.getTime() <= 7 * 24 * 60 * 60 * 1000
}

// 값이 null·undefined 면 "—" 를 보여준다. 0 과 구별하기 위한 것이다.
//   0    — 실제로 0건이다
//   —    — 아직 못 받았거나(로딩) 셀 수 없다(열린 태스크)
// onOpen 이 없으면 이동할 화면이 없는 카드라서 button 이 아니라 div 로 그린다.
// 눌러도 아무 일이 없는 버튼을 두면 고장으로 읽힌다.
function SummaryCard({ label, value, emphasis, note, onOpen }) {
  const className = 'dashboard-summary-card' + (emphasis ? ' is-emphasis' : '') + (onOpen ? ' is-clickable' : '')
  const shown = value === null || value === undefined ? '—' : formatNumber(value)
  const body = <><span>{label}</span><strong>{shown}</strong>{note && <p>{note}</p>}</>
  if (!onOpen) return <section className={className}>{body}</section>
  return <button className={className} type='button' onClick={onOpen}>{body}</button>
}

// 문서 유형 분포. 각 행은 그 유형만 걸러진 문서 목록으로 이동한다.
// null은 URL 전용 __UNCLASSIFIED__ 값으로 보내고 Repository가 IS NULL로 번역한다.
function DocumentTypePanel({ types, total, loaded, onOpenType }) {
  const rows = types ?? []
  const max = rows.reduce((top, row) => Math.max(top, row.count), 0)
  return <section className='panel dashboard-type-panel'>
    <div className='panel-head'><div><h2>문서 유형 분포</h2><p>유형을 선택하면 해당 문서만 모아 볼 수 있습니다.</p></div><span>{rows.length}종</span></div>
    {rows.length
      ? <ul className='dashboard-type-list'>{rows.map(row => {
          const filter = row.document_type ?? UNCLASSIFIED_DOCUMENT_TYPE
          const supported = isSupportedDocumentTypeFilter(filter)
          const label = getDocumentTypeLabel(row.document_type)
          return <li key={filter}>
            <button className='dashboard-type-item' type='button' disabled={!supported} onClick={() => onOpenType(filter)} title={supported ? undefined : '현재 지원하지 않는 문서 유형입니다.'} aria-label={supported ? `${label} 문서 ${formatNumber(row.count)}건 보기` : `${label} 문서 유형 필터 미지원`}>
              <span className={'dashboard-type-name' + (row.document_type ? '' : ' is-unclassified')}>{label}</span>
              <span className='dashboard-type-bar' aria-hidden='true'><i style={{ width: `${max ? (row.count / max) * 100 : 0}%` }}/></span>
              <span className='dashboard-type-count'>{formatNumber(row.count)}건{total ? ` · ${Math.round((row.count / total) * 100)}%` : ''}</span>
            </button>
          </li>
        })}</ul>
      : <div className='dashboard-empty-state'><strong>{loaded ? '집계할 문서가 없습니다.' : '유형 분포를 불러오는 중입니다.'}</strong><p>문서를 업로드하면 유형별 건수가 표시됩니다.</p></div>}
  </section>
}

function RecentDocument({ document, onOpen }) {
  const status = getDocumentStatus(document.status)
  const review = getReviewStatus(document.review_status)
  return <li className='dashboard-document-item'><div><strong>{document.filename}</strong><p>{document.file_type?.toUpperCase()} · {getDocumentTypeLabel(document.document_type)} · {formatDateShort(document.created_at)}</p></div><div className='dashboard-document-statuses'><span className={'status-badge status-' + status.tone}>{status.label}</span><span className={'status-badge status-' + review.tone}>{review.label}</span><button onClick={onOpen}>상세 보기</button></div></li>
}

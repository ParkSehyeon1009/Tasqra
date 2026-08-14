import { useNavigate } from 'react-router-dom'
import PageHeading from '../../components/common/PageHeading'
import { getDocumentPrimaryAction, getDocumentStatus, getReviewStatus } from '../../utils/documentStatus'
import { formatDateShort } from '../../utils/format'
import ActionTaskPanel from './ActionTaskPanel'

export default function DashboardView({ projectId, documents, members }) {
  const navigate = useNavigate()
  const processing = documents.filter(document => ['PENDING', 'EXTRACTING', 'ANALYZING'].includes(document.status))
  const needsReview = documents.filter(document => ['PENDING', 'IN_PROGRESS'].includes(document.review_status))
  const completed = documents.filter(document => document.status === 'COMPLETED')

  return <>
    <PageHeading eyebrow='PROJECT OVERVIEW' title='대시보드' description='지금 확인할 문서와 우선 처리할 액션 태스크를 확인하세요.'/>
    <section className='dashboard-summary-grid dashboard-summary-grid--compact' aria-label='문서 현황 요약'>
      <SummaryCard label='처리 중' value={processing.length}/>
      <SummaryCard label='OCR 검수' value={needsReview.length} emphasis={needsReview.length > 0}/>
      <SummaryCard label='처리 완료' value={completed.length}/>
      <SummaryCard label='참여자' value={members.length}/>
    </section>
    <div className="dashboard-top-grid">
      <section className='panel dashboard-next-actions'><div className='panel-head'><div><h2>OCR 확인 필요</h2><p>검수 후 최종 텍스트에 반영할 문서입니다.</p></div><span>{needsReview.length}건</span></div>
        {needsReview.length ? <ul className='dashboard-document-list'>{needsReview.slice(0, 3).map(document => <NextAction document={document} key={document.id} onOpen={() => navigate(`/projects/${projectId}/documents/${document.id}/review`)}/>)}</ul> : <div className='dashboard-empty-state'><strong>현재 검수가 필요한 문서가 없습니다.</strong><p>검수할 문서가 생기면 이곳에 우선 표시됩니다.</p></div>}
        {needsReview.length > 3 && <div className="dashboard-panel-footer"><span>외 {needsReview.length - 3}건이 더 있습니다.</span><button onClick={() => navigate(`/projects/${projectId}/documents`)}>전체 보기 →</button></div>}
      </section>
      <ActionTaskPanel tasks={[]} onOpenBoard={() => navigate(`/projects/${projectId}/board`)}/>
    </div>
    <section className='panel dashboard-recent-panel'><div className='panel-head'><div><h2>최근 문서</h2><p>최근에 업로드된 문서의 현재 상태입니다.</p></div><span>{documents.length}건</span></div>{documents.length ? <ul className='dashboard-document-list dashboard-recent-list'>{documents.slice(0, 3).map(document => <RecentDocument document={document} key={document.id} onOpen={() => navigate(`/projects/${projectId}/documents/${document.id}`)}/>)}</ul> : <div className='dashboard-empty-state'><strong>등록된 문서가 없습니다.</strong><p>문서 탭에서 파일을 업로드하면 처리 현황이 표시됩니다.</p></div>}
      {documents.length > 3 && <div className="dashboard-panel-footer"><span>외 {documents.length - 3}건이 더 있습니다.</span><button onClick={() => navigate(`/projects/${projectId}/documents`)}>전체 문서 보기 →</button></div>}
    </section>
  </>
}

function SummaryCard({ label, value, emphasis }) {
  return <section className={'dashboard-summary-card' + (emphasis ? ' is-emphasis' : '')}><span>{label}</span><strong>{value}</strong></section>
}

function NextAction({ document, onOpen }) {
  const review = getReviewStatus(document.review_status)
  return <li className='dashboard-document-item'><div><strong>{document.filename}</strong><span className={'status-badge status-' + review.tone}>{review.label}</span><p>{review.description}</p></div><button onClick={onOpen}>{getDocumentPrimaryAction(document)}</button></li>
}

function RecentDocument({ document, onOpen }) {
  const status = getDocumentStatus(document.status)
  const review = getReviewStatus(document.review_status)
  return <li className='dashboard-document-item'><div><strong>{document.filename}</strong><p>{document.file_type?.toUpperCase()} · {formatDateShort(document.created_at)}</p></div><div className='dashboard-document-statuses'><span className={'status-badge status-' + status.tone}>{status.label}</span><span className={'status-badge status-' + review.tone}>{review.label}</span><button onClick={onOpen}>상세 보기</button></div></li>
}

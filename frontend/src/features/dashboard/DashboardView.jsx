import { useNavigate } from 'react-router-dom'
import PageHeading from '../../components/common/PageHeading'
import { getDocumentPrimaryAction, getDocumentStatus, getReviewStatus } from '../../utils/documentStatus'
import { formatDateShort } from '../../utils/format'

export default function DashboardView({ projectId, documents, members }) {
  const navigate = useNavigate()
  const processing = documents.filter(document => ['PENDING', 'EXTRACTING', 'ANALYZING'].includes(document.status))
  const needsReview = documents.filter(document => ['PENDING', 'IN_PROGRESS'].includes(document.review_status))
  const completed = documents.filter(document => document.status === 'COMPLETED')
  const nextUp = [...needsReview, ...processing.filter(document => !needsReview.some(item => item.id === document.id))].slice(0, 4)

  return <>
    <PageHeading eyebrow='PROJECT OVERVIEW' title='대시보드' description='지금 확인할 문서와 다음 작업을 한눈에 확인하세요.'/>
    <section className='dashboard-summary-grid' aria-label='문서 현황 요약'>
      <SummaryCard label='처리 중인 문서' value={processing.length} description='서버에서 처리 상태를 갱신하고 있습니다.'/>
      <SummaryCard label='OCR 검수 필요' value={needsReview.length} description='확인 후 최종 텍스트에 반영할 문서입니다.' emphasis={needsReview.length > 0}/>
      <SummaryCard label='처리 완료 문서' value={completed.length} description='현재 처리 상태가 완료된 문서입니다.'/>
      <SummaryCard label='프로젝트 참여자' value={members.length} description='현재 프로젝트에 참여 중인 사용자입니다.'/>
    </section>
    <section className='panel dashboard-next-actions'><div className='panel-head'><div><h2>지금 할 일</h2><p>문서의 실제 처리·검수 상태를 기준으로 우선순위를 정했습니다.</p></div><span>{nextUp.length}건</span></div>
      {nextUp.length ? <ul className='dashboard-document-list'>{nextUp.map(document => <NextAction document={document} key={document.id} onOpen={() => navigate('/projects/' + projectId + '/documents/' + document.id + (['PENDING', 'IN_PROGRESS'].includes(document.review_status) ? '/review' : ''))}/>)}</ul> : <div className='dashboard-empty-state'><strong>지금 처리할 문서가 없습니다.</strong><p>새 문서를 업로드하거나 완료된 문서를 문서 탭에서 확인해 보세요.</p></div>}
    </section>
    <section className='panel'><div className='panel-head'><div><h2>최근 문서</h2><p>최근에 업로드된 문서의 현재 상태입니다.</p></div><span>{documents.length}건</span></div>{documents.length ? <ul className='dashboard-document-list'>{documents.slice(0, 5).map(document => <RecentDocument document={document} key={document.id} onOpen={() => navigate('/projects/' + projectId + '/documents/' + document.id)}/>)}</ul> : <div className='dashboard-empty-state'><strong>등록된 문서가 없습니다.</strong><p>문서 탭에서 파일을 업로드하면 처리 현황이 표시됩니다.</p></div>}</section>
  </>
}

function SummaryCard({ label, value, description, emphasis }) {
  return <section className={'dashboard-summary-card' + (emphasis ? ' is-emphasis' : '')}><span>{label}</span><strong>{value}</strong><p>{description}</p></section>
}

function NextAction({ document, onOpen }) {
  const status = getDocumentStatus(document.status)
  const review = getReviewStatus(document.review_status)
  return <li className='dashboard-document-item'><div><strong>{document.filename}</strong><span className={'status-badge status-' + (['PENDING', 'IN_PROGRESS'].includes(document.review_status) ? review.tone : status.tone)}>{['PENDING', 'IN_PROGRESS'].includes(document.review_status) ? review.label : status.label}</span><p>{['PENDING', 'IN_PROGRESS'].includes(document.review_status) ? review.description : status.description}</p></div><button onClick={onOpen}>{getDocumentPrimaryAction(document)}</button></li>
}

function RecentDocument({ document, onOpen }) {
  const status = getDocumentStatus(document.status)
  const review = getReviewStatus(document.review_status)
  return <li className='dashboard-document-item'><div><strong>{document.filename}</strong><p>{document.file_type?.toUpperCase()} · {formatDateShort(document.created_at)}</p></div><div className='dashboard-document-statuses'><span className={'status-badge status-' + status.tone}>{status.label}</span><span className={'status-badge status-' + review.tone}>{review.label}</span><button onClick={onOpen}>상세 보기</button></div></li>
}

import { useQuery } from '@tanstack/react-query'
import { getDocument } from '../../api/document'
import LoadingState from '../../components/common/LoadingState'
import './DocumentDetailPanel.css'

export default function DocumentDetailPanel({ projectId, documentId, onClose }) {
  const query = useQuery({
    queryKey: ['projects', projectId, 'documents', documentId],
    queryFn: () => getDocument(projectId, documentId),
    enabled: Boolean(documentId),
  })
  if (!documentId) return null
  const document = query.data
  return <div className="document-detail-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <aside className="document-detail-panel" role="dialog" aria-modal="true" aria-labelledby="document-detail-title">
      <header><div><span>DOCUMENT DETAIL</span><h2 id="document-detail-title">{document?.filename ?? '문서 불러오는 중'}</h2></div><button aria-label="닫기" onClick={onClose}>×</button></header>
      {query.isPending && <LoadingState label="문서 내용을 불러오는 중..."/>}
      {query.isError && <div className="document-detail-error">문서 내용을 불러오지 못했습니다.<button onClick={() => query.refetch()}>다시 시도</button></div>}
      {document && <div className="document-detail-body">
        <dl className="document-meta">
          <div><dt>상태</dt><dd>{statusLabel(document.status)}</dd></div>
          <div><dt>추출 방식</dt><dd>{document.extract_method ?? '-'}</dd></div>
          <div><dt>페이지</dt><dd>{document.page_count ?? 0}</dd></div>
          <div><dt>글자 수</dt><dd>{document.char_count?.toLocaleString() ?? 0}자</dd></div>
        </dl>
        {document.review_status !== 'NOT_REQUIRED' && <section className="review-callout"><div><strong>OCR 검수</strong><p>{reviewLabel(document.review_status)}</p></div><button disabled>검수 화면 준비 중</button></section>}
        <section className="extracted-content"><div><h3>추출된 문서 내용</h3><span>{document.char_count?.toLocaleString() ?? 0}자</span></div>{document.extracted_text ? <pre>{document.extracted_text}</pre> : <p className="empty-text">추출된 텍스트가 없습니다.</p>}</section>
      </div>}
    </aside>
  </div>
}

function statusLabel(status) {
  return { PENDING: '대기 중', EXTRACTING: '텍스트 추출 중', EXTRACTED: '추출 완료', ANALYZING: '분석 중', COMPLETED: '처리 완료', FAILED: '처리 실패' }[status] ?? status
}

function reviewLabel(status) {
  return { PENDING: 'OCR 결과 확인이 필요합니다.', IN_PROGRESS: 'OCR 결과를 검수하고 있습니다.', COMPLETED: 'OCR 검수가 완료되었습니다.' }[status] ?? status
}

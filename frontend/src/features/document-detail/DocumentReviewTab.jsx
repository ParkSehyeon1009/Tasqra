export default function DocumentReviewTab({ document, onOpenReview }) {
  const required = document.review_status !== 'NOT_REQUIRED'
  return <section className="detail-card review-tab"><div className={`review-symbol ${required ? '' : 'muted'}`}>{required ? '◎' : '✓'}</div><h2>{required ? 'OCR 결과 검수' : 'OCR 검수가 필요하지 않은 문서입니다.'}</h2><p>{required ? reviewMessage(document) : '문서 내부 텍스트 레이어를 직접 추출했습니다.'}</p>{document.reviewed_at && <dl><dt>최근 검수</dt><dd>{document.reviewed_by_name ?? '사용자'} · {new Date(document.reviewed_at).toLocaleString()}</dd></dl>}{required && <button className="primary" onClick={onOpenReview}>{document.review_status === 'COMPLETED' ? '검수 결과 확인 및 재수정' : 'OCR 검수 계속하기'}</button>}</section>
}
function reviewMessage(document) { return { PENDING: '원본 이미지와 인식 결과를 비교해 주세요.', IN_PROGRESS: '수정 중인 OCR 결과가 있습니다. 검수를 마무리해 주세요.', COMPLETED: '검수가 완료되었습니다. 필요한 경우 다시 수정할 수 있습니다.' }[document.review_status] }

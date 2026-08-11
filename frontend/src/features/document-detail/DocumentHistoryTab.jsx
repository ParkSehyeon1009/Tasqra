import { useQuery } from '@tanstack/react-query'
import { getDocumentHistory } from '../../api/document'
import LoadingState from '../../components/common/LoadingState'

export default function DocumentHistoryTab({ projectId, document }) {
  const query = useQuery({ queryKey: ['projects', projectId, 'documents', document.id, 'history'], queryFn: () => getDocumentHistory(projectId, document.id) })
  if (query.isPending) return <LoadingState label="변경 이력을 불러오는 중..."/>
  const revisions = query.data ?? []
  return <section className="detail-card history-tab"><h2>문서 변경 이력</h2><div className="timeline"><HistoryItem title="문서 업로드 및 텍스트 추출" person={document.uploaded_by_name} date={document.created_at}/>{revisions.map(item => <RevisionItem key={item.id} revision={item}/>)}{document.reviewed_at && <HistoryItem title="OCR 검수 완료" person={document.reviewed_by_name} date={document.reviewed_at}/>}</div></section>
}
function HistoryItem({ title, person, date }) { return <article><i/><div><strong>{title}</strong><small>{person ?? '알 수 없는 사용자'} · {new Date(date).toLocaleString()}</small></div></article> }
function RevisionItem({ revision }) { return <article><i/><div><div className="revision-heading"><strong>OCR 텍스트 수정 · v{revision.from_version} → v{revision.to_version}</strong><span>{revision.changed_by_name ?? '알 수 없는 사용자'}</span></div><small>{new Date(revision.created_at).toLocaleString()}</small><details><summary>수정 상세보기</summary><dl className="revision-detail"><dt>수정 전</dt><dd>{revision.before_text}</dd><dt>수정 후</dt><dd>{revision.after_text}</dd></dl></details></div></article> }

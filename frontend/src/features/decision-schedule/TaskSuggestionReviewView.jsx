import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { approveTaskSuggestion, getPendingTaskSuggestions, getRejectedTaskSuggestions, getTaskSuggestions, rejectTaskSuggestion } from '../../api/taskSuggestion'

export default function TaskSuggestionReviewPanel({ projectId, documentId, canEdit, notify }) {
  const queryClient = useQueryClient()
  const key = ['projects', projectId, 'documents', documentId, 'task-suggestion-review']
  const pending = useQuery({ queryKey: [...key, 'pending'], queryFn: () => getPendingTaskSuggestions(projectId, documentId), retry: false })
  const approved = useQuery({ queryKey: [...key, 'approved'], queryFn: () => getTaskSuggestions(projectId, documentId), retry: false })
  const rejected = useQuery({ queryKey: [...key, 'rejected'], queryFn: () => getRejectedTaskSuggestions(projectId, documentId), retry: false })
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: key })
    queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'tasks'] })
    queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'dashboard'] })
  }
  const action = useMutation({
    mutationFn: ({ item, kind }) => kind === 'approve' ? approveTaskSuggestion(projectId, item.id) : rejectTaskSuggestion(projectId, item.id),
    onSuccess: (row, variables) => notify?.('success', variables.kind === 'approve' ? '액션 태스크 생성 완료' : '제안 거절 완료', variables.kind === 'approve' ? `${row.title} 태스크가 보드에 생성됐습니다.` : row.title),
    onError: error => notify?.('error', '처리하지 못했습니다', error.message),
    onSettled: refresh,
  })
  const items = pending.data?.items ?? []
  const total = (pending.data?.total ?? 0) + (approved.data?.total ?? 0) + (rejected.data?.total ?? 0)
  return <section className='decision-schedule-panel' aria-label='이 문서에서 제안한 액션 태스크'>
    <header className='decision-schedule-panel__heading'><div className='review-title-line'><div><span>AI 업무 제안</span><h2>액션 태스크 후보 <b>{total}</b></h2></div>{!canEdit && <strong>읽기 전용</strong>}</div><p>원문에서 실제로 수행할 일만 골랐습니다. 승인하면 보드에 태스크가 생성됩니다.</p></header>
    <section className='action-item-review'>
      {pending.isPending && <p className='review-empty'>불러오는 중입니다.</p>}
      {pending.isError && <p className='review-empty' role='alert'>{pending.error.message}</p>}
      {!pending.isPending && !pending.isError && items.length === 0 && <p className='review-empty'>승인 대기 액션 태스크가 없습니다.</p>}
      {items.map(item => <article className='review-card' key={item.id}>
        <div className='review-card__meta'><span>근거 점수 {Math.round(Number(item.quality_score) * 100)}</span>{item.due_on && <span>마감 {item.due_on}</span>}</div>
        <h3>{item.title}</h3>
        {item.description && <p>{item.description}</p>}
        <details className='review-evidence'><summary>원문 근거 보기</summary><blockquote>{item.evidence_text}</blockquote></details>
        {canEdit && <div className='review-card__actions'><button className='primary' disabled={action.isPending} onClick={() => action.mutate({ item, kind: 'approve' })}>승인하고 태스크 생성</button><button disabled={action.isPending} onClick={() => action.mutate({ item, kind: 'reject' })}>거절</button></div>}
      </article>)}
    </section>
  </section>
}

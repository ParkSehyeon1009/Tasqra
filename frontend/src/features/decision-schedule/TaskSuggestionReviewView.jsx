import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { approveTaskSuggestion, getPendingTaskSuggestions, getRejectedTaskSuggestions, getTaskSuggestions, rejectTaskSuggestion } from '../../api/taskSuggestion'
// ⚠️ 옆 패널(DecisionScheduleReviewView)과 **같은 스타일시트를 쓴다.** 두 패널이
//   한 화면에 나란히 붙으므로 생김새가 갈리면 안 된다. 전용 CSS 를 새로 만들면
//   그 순간 스타일이 두 벌이 되어 한쪽만 고쳐지는 일이 생긴다.
//
// 🔴 2026-09-07: 처음에는 BEM 표기(review-card__actions·primary)로 썼는데
//   이 CSS 는 하이픈 표기(review-actions·is-primary)다. 그래서 카드 테두리만
//   먹고 버튼·메타·빈 상태가 전부 스타일 없이 떴다. **CSS 에 없는 클래스는
//   조용히 무시된다** — 새 이름을 쓸 때는 CSS 에 있는지 먼저 확인할 것.
import './DecisionScheduleReviewView.css'

// 카드를 성격별로 묶는다. 과업지시서 한 건에서 20건 넘게 나오는데, 한 줄로
// 늘어놓으면 무엇부터 볼지 알 수 없다. **개수를 줄이는 게 아니라 읽는 단위를
// 만드는 것**이다 — 합쳐서 지우면 과업이 사라지고 아무도 못 알아챈다.
//
// 순서에 뜻이 있다. 위에서부터 「무슨 일을 하는가 -> 언제까지 무엇을 내는가」다.
const GROUPS = [
  { key: 'scope', label: '과업 범위', hint: '사업으로 수행할 일',
    match: item => item.statement_type === 'SCOPE' },
  { key: 'deliverable', label: '제출·납품', hint: '기한이 붙는 산출물',
    match: item => ['SUBMISSION', 'DELIVERABLE'].includes(item.task_kind) },
  { key: 'reporting', label: '보고·점검', hint: '주기적으로 알리거나 확인할 일',
    match: item => ['REPORTING', 'REVIEW'].includes(item.task_kind) },
  // 위 어디에도 안 걸린 것. 빈 묶음은 그리지 않으므로 평소엔 안 보인다.
  { key: 'etc', label: '그 밖의 의무', hint: '', match: () => true },
]

function groupItems(items) {
  const buckets = new Map(GROUPS.map(g => [g.key, []]))
  for (const item of items) {
    const group = GROUPS.find(g => g.match(item)) ?? GROUPS[GROUPS.length - 1]
    buckets.get(group.key).push(item)
  }
  return GROUPS.map(g => ({ ...g, items: buckets.get(g.key) })).filter(g => g.items.length > 0)
}

const DECISION_LABELS = { PENDING: '승인 대기', APPROVED: '반영됨', EDITED: '수정 반영', REJECTED: '거절됨' }

export default function TaskSuggestionReviewPanel({ projectId, documentId, canEdit, notify }) {
  const queryClient = useQueryClient()
  const key = ['projects', projectId, 'documents', documentId, 'task-suggestion-review']
  const pending = useQuery({ queryKey: [...key, 'pending'], queryFn: () => getPendingTaskSuggestions(projectId, documentId), retry: false })
  const approved = useQuery({ queryKey: [...key, 'approved'], queryFn: () => getTaskSuggestions(projectId, documentId), retry: false })
  const rejected = useQuery({ queryKey: [...key, 'rejected'], queryFn: () => getRejectedTaskSuggestions(projectId, documentId), retry: false })

  // 옆 패널과 같은 상태 탭. 승인·거절한 것도 다시 볼 수 있어야 하고,
  // 20건이 한 화면에 쏟아지지 않는다.
  const [activeState, setActiveState] = useState('pending')
  const views = {
    pending: { label: '승인 대기', query: pending, empty: '승인 대기 액션 태스크가 없습니다.' },
    approved: { label: '반영됨', query: approved, empty: '아직 태스크로 만든 제안이 없습니다.' },
    rejected: { label: '거절됨', query: rejected, empty: '거절한 제안이 없습니다.' },
  }
  const view = views[activeState]
  const items = view.query.data?.items ?? []
  const total = Object.values(views).reduce((sum, v) => sum + (v.query.data?.total ?? 0), 0)

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

  // ⚠️ suggestion-panel 은 **이 패널에만** 스크롤·묶음 스타일을 걸기 위한
  //   구분자다. decision-schedule-panel 은 옆 패널과 공유하므로 거기에 높이를
  //   주면 결정·일정 쪽까지 잘린다.
  return <section className='decision-schedule-panel suggestion-panel' aria-label='이 문서에서 제안한 액션 태스크'>
    <header className='decision-schedule-panel__heading'>
      <div className='review-title-line'>
        <div><span>AI 업무 제안</span><h2>액션 태스크 후보 <b>{total}</b></h2></div>
        {!canEdit && <strong>읽기 전용</strong>}
      </div>
      <p>원문에서 실제로 수행할 일만 골랐습니다. 승인하면 보드에 태스크가 생성됩니다.</p>
    </header>

    <nav className='review-state-tabs' aria-label='액션 태스크 제안 상태'>
      {Object.entries(views).map(([stateKey, v]) => <button
        type='button'
        key={stateKey}
        className={activeState === stateKey ? 'is-active' : ''}
        aria-pressed={activeState === stateKey}
        onClick={() => setActiveState(stateKey)}
      ><span>{v.label}</span><b>{v.query.data?.total ?? 0}</b></button>)}
    </nav>

    <section className='action-item-review'>
      <div className='review-list-body'>
        {view.query.isPending && <p className='review-empty'>불러오는 중입니다.</p>}
        {view.query.isError && <p className='review-empty' role='alert'>{view.query.error.message}</p>}
        {!view.query.isPending && !view.query.isError && items.length === 0 && <p className='review-empty'>{view.empty}</p>}
        {groupItems(items).map(group => <section className='suggestion-group' key={group.key}>
          <h3 className='suggestion-group__head'>
            {group.label} <b>{group.items.length}</b>
            {group.hint && <span>{group.hint}</span>}
          </h3>
          <div className='review-card-list'>
            {group.items.map(item => <article className='review-card' key={item.id}>
              <div className='review-card-main'>
                <div className='review-card-title'>
                  {/* 묶음 제목이 성격을 말해주므로 배지는 뽑은 근거만 알린다.
                      SCOPE(features)는 생성이라 원문 인용이 없고,
                      그 밖(action_task)은 원문 문장에서 고른 것이다. */}
                  <span className='review-card-kind'>{item.statement_type === 'SCOPE' ? '요약' : '원문'}</span>
                  <strong>{item.title}</strong>
                </div>
                <div className='review-card-meta'>
                  <span>{DECISION_LABELS[item.decision] ?? item.decision}</span>
                  <span>근거 점수 {Math.round(Number(item.quality_score) * 100)}</span>
                  {item.due_on && <span>마감 {item.due_on}</span>}
                  {item.actor && <span>{item.actor}</span>}
                </div>
                {item.description && <p>{item.description}</p>}
                {item.evidence_text && <details className='review-evidence'><summary>원문 근거 보기</summary><blockquote>{item.evidence_text}</blockquote></details>}
                {item.reason && <small className='review-card-reason'><b>AI 판단</b>{item.reason}</small>}
              </div>
              {/* 승인·거절은 대기 중인 것에만 뜬다. 이미 처리한 카드는 읽기용이다. */}
              {canEdit && item.decision === 'PENDING' && <div className='review-actions'>
                <button type='button' className='is-primary' disabled={action.isPending} onClick={() => action.mutate({ item, kind: 'approve' })}>{action.isPending ? '처리 중…' : '승인'}</button>
                <button type='button' disabled={action.isPending} onClick={() => action.mutate({ item, kind: 'reject' })}>거절</button>
              </div>}
            </article>)}
          </div>
        </section>)}
      </div>
    </section>
  </section>
}

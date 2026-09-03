// =============================================================================
// 이 파일의 책임: 문서에서 추출한 결정사항·일정을 카드 목록으로 검토한다.
// 다른 파일과의 관계: api/decisionSchedule.js의 두 도메인 API를 문서 ID로 조회해
//   화면에서 합치고, 상태 변경 뒤 문서별 목록·대시보드·산출물 query를 무효화한다.
// Spring 비교: 서로 다른 두 Controller 응답을 하나의 화면 DTO처럼 조립하는 하위
//   View이며, 저장할 때는 각 원래 Controller API로 다시 보낸다.
// =============================================================================

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  approveDecision,
  approveScheduleItem,
  cancelDecision,
  cancelScheduleItem,
  getDecisions,
  getPendingDecisions,
  getPendingScheduleItems,
  getRejectedDecisions,
  getRejectedScheduleItems,
  getScheduleItems,
  rejectDecision,
  rejectScheduleItem,
  updateDecision,
  updateScheduleItem,
} from '../../api/decisionSchedule'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import './DecisionScheduleReviewView.css'

const DECISION_LABELS = {
  PENDING: '승인 대기',
  APPROVED: '승인',
  EDITED: '수정 승인',
  REJECTED: '거절',
}
const STATUS_LABELS = { DECIDED: '결정됨', PENDING: '미결 안건', REVERSED: '뒤집힘' }
const KIND_LABELS = { MILESTONE: '주요 시점', DEADLINE: '기한', MEETING: '회의', PERIOD: '기간' }

const RESOURCES = [
  {
    key: 'decision',
    getApproved: getDecisions,
    getPending: getPendingDecisions,
    getRejected: getRejectedDecisions,
    approve: approveDecision,
    reject: rejectDecision,
    cancel: cancelDecision,
    update: updateDecision,
  },
  {
    key: 'schedule',
    getApproved: getScheduleItems,
    getPending: getPendingScheduleItems,
    getRejected: getRejectedScheduleItems,
    approve: approveScheduleItem,
    reject: rejectScheduleItem,
    cancel: cancelScheduleItem,
    update: updateScheduleItem,
  },
]

export default function DecisionScheduleReviewPanel({ projectId, documentId, canEdit, notify }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(null)
  const [rejectTarget, setRejectTarget] = useState(null)
  const [activeState, setActiveState] = useState('pending')
  const decisionReview = useResourceQueries(RESOURCES[0], projectId, documentId)
  const scheduleReview = useResourceQueries(RESOURCES[1], projectId, documentId)
  const reviews = [decisionReview, scheduleReview]

  const pendingItems = mergeItems(reviews, 'pending')
  const approvedItems = mergeItems(reviews, 'approved')
  const rejectedItems = mergeItems(reviews, 'rejected')
  const pendingQueries = reviews.map(review => review.pending)
  const approvedQueries = reviews.map(review => review.approved)
  const rejectedQueries = reviews.map(review => review.rejected)
  const stateViews = {
    pending: { label: '승인 대기', items: pendingItems, queries: pendingQueries, empty: '승인 대기 결정사항·일정이 없습니다.' },
    approved: { label: '반영됨', items: approvedItems, queries: approvedQueries, empty: '산출물에 반영된 결정사항·일정이 없습니다.' },
    rejected: { label: '거절됨', items: rejectedItems, queries: rejectedQueries, empty: '거절된 결정사항·일정이 없습니다.' },
  }
  const activeView = stateViews[activeState]
  const totalItems = Object.values(stateViews).reduce((sum, view) => sum + sumTotal(view.queries), 0)

  const invalidate = resource => {
    const workspaceProjectId = Number(projectId)
    queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId, `${resource.key}-review`] })
    queryClient.invalidateQueries({ queryKey: ['projects', workspaceProjectId, 'dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['projects', workspaceProjectId, 'deliverable-preview'] })
    if (resource.key === 'schedule') {
      queryClient.invalidateQueries({ queryKey: ['projects', workspaceProjectId, 'calendar'] })
    }
  }

  const actionMutation = useMutation({
    mutationFn: ({ item, action }) => item.resource[action](projectId, item.row.id),
    onSuccess: (_row, variables) => {
      const messages = {
        approve: ['승인했습니다', '산출물에 반영됩니다.'],
        reject: ['거절했습니다', '산출물에서 제외됩니다.'],
        cancel: variables.item.row.decision === 'REJECTED'
          ? ['되살렸습니다', '승인 대기로 되돌렸습니다.']
          : ['승인을 취소했습니다', '승인 대기로 되돌렸습니다.'],
      }
      notify?.('success', messages[variables.action][0], `${variables.item.row.title} — ${messages[variables.action][1]}`)
    },
    onError: error => notify?.('error', '처리하지 못했습니다', error?.message),
    onSettled: (_data, _error, variables) => variables && invalidate(variables.item.resource),
  })

  const updateMutation = useMutation({
    mutationFn: ({ item, changes }) => item.resource.update(projectId, item.row.id, changes),
    onSuccess: row => {
      notify?.('success', '수정 승인했습니다', `${row.title} — 산출물에 반영됩니다.`)
      setEditing(null)
    },
    onError: error => notify?.('error', '수정하지 못했습니다', error?.message),
    onSettled: (_data, _error, variables) => variables && invalidate(variables.item.resource),
  })

  const busyKey = actionMutation.isPending ? itemKey(actionMutation.variables?.item) : null
  const editingKey = itemKey(editing)
  const reviewLocked = actionMutation.isPending || updateMutation.isPending

  return <section className='decision-schedule-panel' aria-label='이 문서에서 추출한 결정사항과 일정'>
    <header className='decision-schedule-panel__heading'>
      <div className='review-title-line'>
        <div><span>AI 추출 결과</span><h2>결정사항·일정 <b>{totalItems}</b></h2></div>
        {!canEdit && <strong>읽기 전용</strong>}
      </div>
      <p>결정사항과 일정을 카드별로 검토합니다.</p>
    </header>

    <nav className='review-state-tabs' aria-label='결정사항과 일정 상태'>
      {Object.entries(stateViews).map(([key, view]) => <button
        type='button'
        key={key}
        className={activeState === key ? 'is-active' : ''}
        aria-pressed={activeState === key}
        onClick={() => { setActiveState(key); setEditing(null) }}
      ><span>{view.label}</span><b>{sumTotal(view.queries)}</b></button>)}
    </nav>

    <section className='action-item-review'>
      <ReviewList queries={activeView.queries} items={activeView.items} empty={activeView.empty}>
        {activeView.items.map(item => <ReviewCard
          key={itemKey(item)}
          item={item}
          canEdit={canEdit}
          disabled={reviewLocked}
          busy={busyKey === itemKey(item) || (updateMutation.isPending && itemKey(updateMutation.variables?.item) === itemKey(item))}
          actions={activeState}
          editing={editingKey === itemKey(item)}
          onApprove={() => actionMutation.mutate({ item, action: 'approve' })}
          onReject={() => setRejectTarget(item)}
          onEdit={() => setEditing(item)}
          onCancel={() => actionMutation.mutate({ item, action: 'cancel' })}
          onRestore={() => actionMutation.mutate({ item, action: 'cancel' })}
          editForm={editingKey === itemKey(item) ? <EditForm
            type={item.resource.key}
            row={item.row}
            saving={updateMutation.isPending}
            notify={notify}
            onClose={() => setEditing(null)}
            onSave={changes => updateMutation.mutate({ item, changes })}
          /> : null}
        />)}
      </ReviewList>
    </section>

    <ConfirmDialog
      open={Boolean(rejectTarget)}
      title='이 제안을 거절할까요?'
      message={rejectTarget ? `“${rejectTarget.row.title}”은 산출물에서 제외되며 거절함에서 되살릴 수 있습니다.` : ''}
      confirmLabel='거절'
      danger
      onCancel={() => setRejectTarget(null)}
      onConfirm={() => {
        actionMutation.mutate({ item: rejectTarget, action: 'reject' })
        setRejectTarget(null)
      }}
    />
  </section>
}

function useResourceQueries(resource, projectId, documentId) {
  const baseKey = `${resource.key}-review`
  const approved = useQuery({
    queryKey: ['projects', projectId, 'documents', documentId, baseKey, 'approved'],
    queryFn: () => resource.getApproved(projectId, { documentId }),
    retry: false,
  })
  const pending = useQuery({
    queryKey: ['projects', projectId, 'documents', documentId, baseKey, 'pending'],
    queryFn: () => resource.getPending(projectId, { documentId }),
    retry: false,
  })
  const rejected = useQuery({
    queryKey: ['projects', projectId, 'documents', documentId, baseKey, 'rejected'],
    queryFn: () => resource.getRejected(projectId, { documentId }),
    retry: false,
  })
  return { resource, approved, pending, rejected }
}

function mergeItems(reviews, state) {
  return reviews.flatMap(review => (review[state].data?.items ?? []).map(row => ({ resource: review.resource, row })))
}

function sumTotal(queries) {
  return queries.reduce((sum, query) => sum + (query.data?.total ?? 0), 0)
}

function itemKey(item) {
  return item ? `${item.resource.key}-${item.row.id}` : null
}

function ReviewList({ queries, items, empty, children }) {
  const pending = queries.some(query => query.isPending)
  const errors = queries.filter(query => query.isError)
  const total = sumTotal(queries)
  const returned = queries.reduce((sum, query) => sum + (query.data?.returned ?? 0), 0)
  const truncated = queries.some(query => query.data?.truncated)
  return <div className='review-list-body'>
    {pending && <p className='review-empty'>불러오는 중입니다.</p>}
    {errors.map((query, index) => <p className='review-empty' key={index}>일부 항목을 불러오지 못했습니다. {query.error?.message}</p>)}
    {!pending && errors.length === 0 && items.length === 0 && <p className='review-empty'>{empty}</p>}
    {items.length > 0 && <div className='review-card-list'>{children}</div>}
    {truncated && <p className='review-limit'>전체 {total}건 중 {returned}건만 보여줍니다.</p>}
  </div>
}

function ReviewCard({ item, canEdit, disabled, busy, actions, editing, onApprove, onReject, onEdit, onCancel, onRestore, editForm }) {
  const { resource, row } = item
  const locked = disabled || busy || !canEdit
  const confidence = confidenceLabel(row.confidence)
  const scheduleDate = resource.key === 'schedule' ? scheduleDates(row) : null
  return <article className={`review-card${row.stale ? ' is-stale' : ''}`}>
    <div className='review-card-main'>
      <div className='review-card-title'>
        <span className='review-card-kind'>{itemTypeLabel(item)}</span>
        <strong>{row.title}</strong>
      </div>
      <div className='review-card-meta'>
        <span>{DECISION_LABELS[row.decision] ?? row.decision}</span>
        {resource.key === 'decision' && <span>{STATUS_LABELS[row.status] ?? row.status}</span>}
        {scheduleDate && <span>{scheduleDate}</span>}
        {confidence && <span>{confidence}</span>}
      </div>
      {resource.key === 'decision' && row.content && <p>{row.content}</p>}
      {row.evidence_text && <details className='review-evidence'><summary>원문 근거 보기</summary><blockquote>{row.evidence_text}</blockquote></details>}
      {row.reason && <small className='review-card-reason'><b>AI 판단</b>{row.reason}</small>}
      {row.filename && <small className='review-card-source'>{row.filename}</small>}
      {row.stale && <em>{actions === 'rejected'
        ? '원문이 수정된 뒤의 오래된 제안입니다. 다시 분석하기 전에는 되살릴 수 없습니다.'
        : '원문이 수정된 뒤의 오래된 제안입니다. 승인·수정할 수 없지만 거절·취소로 산출물에서 뺄 수 있습니다.'}</em>}
    </div>
    {canEdit && <div className='review-actions'>
      {actions === 'pending' && <>
        <button type='button' className='is-primary' disabled={locked || row.stale} onClick={onApprove}>{busy ? '처리 중…' : '승인'}</button>
        <button type='button' disabled={locked} onClick={onReject}>거절</button>
      </>}
      {actions === 'approved' && <>
        <button type='button' disabled={locked || row.stale || editing} onClick={onEdit}>{editing ? '수정 중' : '수정'}</button>
        <button type='button' disabled={locked || editing} onClick={onCancel}>{busy ? '처리 중…' : '승인 취소'}</button>
      </>}
      {actions === 'rejected' && <button type='button' disabled={locked || row.stale} onClick={onRestore}>{busy ? '처리 중…' : '되살리기'}</button>}
    </div>}
    {editForm}
  </article>
}

function confidenceLabel(value) {
  if (value === null || value === undefined || value === '') return null
  const confidence = Number(value)
  if (!Number.isFinite(confidence)) return null
  const percent = confidence <= 1 ? confidence * 100 : confidence
  return `확신 ${Math.round(percent)}%`
}

function itemTypeLabel(item) {
  if (item.resource.key === 'decision') return '결정사항'
  return KIND_LABELS[item.row.kind] ?? item.row.kind
}

function EditForm({ type, row, saving, notify, onClose, onSave }) {
  const [form, setForm] = useState(type === 'decision'
    ? { title: row.title, content: row.content ?? '', status: row.status, decided_on: row.decided_on ?? '' }
    : { title: row.title, kind: row.kind, starts_on: row.starts_on ?? '', ends_on: row.ends_on ?? '' })
  const set = (field, value) => setForm(current => ({ ...current, [field]: value }))
  const submit = event => {
    event.preventDefault()
    const initial = type === 'decision'
      ? { title: row.title, content: row.content ?? '', status: row.status, decided_on: row.decided_on ?? '' }
      : { title: row.title, kind: row.kind, starts_on: row.starts_on ?? '', ends_on: row.ends_on ?? '' }
    const changes = {}
    for (const [field, value] of Object.entries(form)) {
      if (value === initial[field]) continue
      changes[field] = ['content', 'decided_on', 'starts_on', 'ends_on'].includes(field) && value === '' ? null : value
    }
    if (Object.keys(changes).length === 0) {
      notify?.('info', '바뀐 값이 없습니다', '고칠 값을 하나 이상 바꿔 주세요.')
      return
    }
    onSave(changes)
  }
  return <form className='review-edit' onSubmit={submit}>
    <h4>{row.title} 수정</h4>
    <label><span>제목</span><input required maxLength={300} value={form.title} onChange={event => set('title', event.target.value)}/></label>
    {type === 'decision' ? <>
      <label><span>내용</span><textarea rows={3} value={form.content} onChange={event => set('content', event.target.value)}/></label>
      <label><span>결정 자체 상태</span><select value={form.status} onChange={event => set('status', event.target.value)}>
        {Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label><span>결정일</span><input type='date' value={form.decided_on} onChange={event => set('decided_on', event.target.value)}/></label>
    </> : <>
      <label><span>종류</span><select value={form.kind} onChange={event => set('kind', event.target.value)}>
        {Object.entries(KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label><span>시작일</span><input type='date' value={form.starts_on} onChange={event => set('starts_on', event.target.value)}/></label>
      <label><span>종료일</span><input type='date' value={form.ends_on} onChange={event => set('ends_on', event.target.value)}/></label>
    </>}
    <p>저장하면 사람이 확인한 값(EDITED)으로 남고 기존 산출물 count/list에 반영됩니다.</p>
    <div><button type='submit' className='is-primary' disabled={saving}>{saving ? '저장 중…' : '수정 승인'}</button><button type='button' disabled={saving} onClick={onClose}>닫기</button></div>
  </form>
}

function scheduleDates(row) {
  if (!row.starts_on && !row.ends_on) return null
  if (row.starts_on && row.ends_on) return `${row.starts_on} ~ ${row.ends_on}`
  return row.starts_on ? `시작 ${row.starts_on}` : `종료 ${row.ends_on}`
}

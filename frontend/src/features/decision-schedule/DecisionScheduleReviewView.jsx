// =============================================================================
// 이 파일의 책임: 결정사항·일정 제안의 승인 대기, 승인됨, 거절함을 한 화면에서 검토한다.
// 다른 파일과의 관계: api/decisionSchedule.js를 React Query로 호출하고, 변경 뒤
//   대시보드와 산출물 미리보기 query까지 무효화해 count/list를 다시 받는다.
// Spring 비교: 서버 DTO를 표시하고 Controller API를 호출하는 MVC View 계층이다.
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
import PageHeading from '../../components/common/PageHeading'
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
    title: '결정사항',
    description: '결정 자체의 상태와 AI 제안 승인 상태를 구분해 검토합니다.',
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
    title: '일정·기한',
    description: '문서에 없는 날짜는 비워 두며 임의로 만들어 채우지 않습니다.',
    getApproved: getScheduleItems,
    getPending: getPendingScheduleItems,
    getRejected: getRejectedScheduleItems,
    approve: approveScheduleItem,
    reject: rejectScheduleItem,
    cancel: cancelScheduleItem,
    update: updateScheduleItem,
  },
]

export default function DecisionScheduleReviewView({ projectId, canEdit, notify }) {
  return <>
    <PageHeading
      eyebrow='REVIEW'
      title='결정·일정'
      description='승인하거나 수정 승인한 항목만 산출물에 반영됩니다.'
    />
    {!canEdit && <p className='review-readonly'>VIEWER는 내용을 볼 수 있지만 승인 상태를 바꿀 수 없습니다.</p>}
    <div className='review-resource-list'>
      {RESOURCES.map(resource => <ReviewSection
        key={resource.key}
        resource={resource}
        projectId={projectId}
        canEdit={canEdit}
        notify={notify}
      />)}
    </div>
  </>
}

function ReviewSection({ resource, projectId, canEdit, notify }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(null)
  const [rejectTarget, setRejectTarget] = useState(null)
  const [rejectedOpen, setRejectedOpen] = useState(false)
  const baseKey = `${resource.key}-review`
  const approvedQuery = useQuery({
    queryKey: ['projects', projectId, baseKey, 'approved'],
    queryFn: () => resource.getApproved(projectId),
    retry: false,
  })
  const pendingQuery = useQuery({
    queryKey: ['projects', projectId, baseKey, 'pending'],
    queryFn: () => resource.getPending(projectId),
    retry: false,
  })
  const rejectedQuery = useQuery({
    queryKey: ['projects', projectId, baseKey, 'rejected'],
    queryFn: () => resource.getRejected(projectId),
    retry: false,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['projects', projectId, baseKey] })
    queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'dashboard'] })
    queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'deliverable-preview'] })
    queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'deliverable-content'] })
  }

  const actionMutation = useMutation({
    mutationFn: ({ row, action }) => resource[action](projectId, row.id),
    onSuccess: (_row, variables) => {
      const messages = {
        approve: ['승인했습니다', '산출물에 반영됩니다.'],
        reject: ['거절했습니다', '산출물에서 제외됩니다.'],
        cancel: variables.row.decision === 'REJECTED'
          ? ['되살렸습니다', '승인 대기로 되돌렸습니다.']
          : ['승인을 취소했습니다', '승인 대기로 되돌렸습니다.'],
      }
      notify?.('success', messages[variables.action][0], `${variables.row.title} — ${messages[variables.action][1]}`)
    },
    onError: error => notify?.('error', '처리하지 못했습니다', error?.message),
    onSettled: invalidate,
  })

  const updateMutation = useMutation({
    mutationFn: ({ row, changes }) => resource.update(projectId, row.id, changes),
    onSuccess: row => {
      notify?.('success', '수정 승인했습니다', `${row.title} — 산출물에 반영됩니다.`)
      setEditing(null)
    },
    onError: error => notify?.('error', '수정하지 못했습니다', error?.message),
    onSettled: invalidate,
  })

  const pendingRows = pendingQuery.data?.items ?? []
  const approvedRows = approvedQuery.data?.items ?? []
  const rejectedRows = rejectedQuery.data?.items ?? []
  const busyId = actionMutation.isPending ? actionMutation.variables?.row.id : null

  return <section className='panel review-resource' aria-label={resource.title}>
    <div className='review-heading'>
      <div><h2>{resource.title}</h2><p>{resource.description}</p></div>
      <dl>
        <div><dt>승인 대기</dt><dd>{pendingQuery.data?.total ?? 0}</dd></div>
        <div><dt>반영 중</dt><dd>{approvedQuery.data?.total ?? 0}</dd></div>
      </dl>
    </div>

    <ReviewGroup title='승인 대기' note='승인은 원문 값 그대로 인정하고, 거절은 산출물에서 제외합니다.' query={pendingQuery} empty='승인 대기 항목이 없습니다.'>
      {pendingRows.map(row => <ReviewCard
        key={row.id}
        row={row}
        type={resource.key}
        canEdit={canEdit}
        busy={busyId === row.id}
        actions='pending'
        onApprove={() => actionMutation.mutate({ row, action: 'approve' })}
        onReject={() => setRejectTarget(row)}
      />)}
    </ReviewGroup>

    <ReviewGroup title='산출물 반영 항목' note='APPROVED와 EDITED만 이 목록과 기존 산출물 count/list에 포함됩니다.' query={approvedQuery} empty='승인된 항목이 없습니다.'>
      {approvedRows.map(row => <ReviewCard
        key={row.id}
        row={row}
        type={resource.key}
        canEdit={canEdit}
        busy={busyId === row.id || (updateMutation.isPending && updateMutation.variables?.row.id === row.id)}
        actions='approved'
        editing={editing?.id === row.id}
        onEdit={() => setEditing(row)}
        onCancel={() => actionMutation.mutate({ row, action: 'cancel' })}
      />)}
      {editing && <EditForm
        key={`${resource.key}-${editing.id}`}
        type={resource.key}
        row={editing}
        saving={updateMutation.isPending}
        notify={notify}
        onClose={() => setEditing(null)}
        onSave={changes => updateMutation.mutate({ row: editing, changes })}
      />}
    </ReviewGroup>

    {!rejectedQuery.isPending && !rejectedQuery.isError && rejectedRows.length > 0 && <div className='review-rejected'>
      <button type='button' className='review-rejected-toggle' aria-expanded={rejectedOpen} onClick={() => setRejectedOpen(value => !value)}>
        {rejectedOpen ? '거절된 항목 숨기기' : `거절된 항목 보기 (${rejectedQuery.data.total}건)`}
      </button>
      {rejectedOpen && <div className='review-card-list'>
        {rejectedRows.map(row => <ReviewCard
          key={row.id}
          row={row}
          type={resource.key}
          canEdit={canEdit}
          busy={busyId === row.id}
          actions='rejected'
          onRestore={() => actionMutation.mutate({ row, action: 'cancel' })}
        />)}
      </div>}
    </div>}

    <ConfirmDialog
      open={Boolean(rejectTarget)}
      title={`${resource.title}을(를) 거절할까요?`}
      message={rejectTarget ? `“${rejectTarget.title}”은 산출물에서 제외되며 거절함에서 되살릴 수 있습니다.` : ''}
      confirmLabel='거절'
      danger
      onCancel={() => setRejectTarget(null)}
      onConfirm={() => {
        actionMutation.mutate({ row: rejectTarget, action: 'reject' })
        setRejectTarget(null)
      }}
    />
  </section>
}

function ReviewGroup({ title, note, query, empty, children }) {
  return <section className='review-group'>
    <div className='review-group-heading'><h3>{title}</h3><span>{note}</span></div>
    {query.isPending && <p className='review-empty'>불러오는 중입니다.</p>}
    {query.isError && <p className='review-empty'>불러오지 못했습니다. {query.error?.message}</p>}
    {!query.isPending && !query.isError && query.data?.items?.length === 0 && <p className='review-empty'>{empty}</p>}
    {!query.isPending && !query.isError && query.data?.items?.length > 0 && <div className='review-card-list'>{children}</div>}
    {query.data?.truncated && <p className='review-limit'>전체 {query.data.total}건 중 {query.data.returned}건만 보여줍니다.</p>}
  </section>
}

function ReviewCard({ row, type, canEdit, busy, actions, editing, onApprove, onReject, onEdit, onCancel, onRestore }) {
  const locked = busy || !canEdit
  return <article className={`review-card${row.stale ? ' is-stale' : ''}`}>
    <div className='review-card-main'>
      <div className='review-card-title'>
        <strong>{row.title}</strong>
        <span>{DECISION_LABELS[row.decision] ?? row.decision}</span>
        {type === 'decision' && <span>{STATUS_LABELS[row.status] ?? row.status}</span>}
        {type === 'schedule' && <span>{KIND_LABELS[row.kind] ?? row.kind}</span>}
      </div>
      {type === 'decision'
        ? <p>{row.content || '세부 내용 없음'}</p>
        : <p>{scheduleDates(row)}</p>}
      <small>{row.filename || '출처 문서 삭제됨'} · 근거: {row.reason}</small>
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
        <button type='button' disabled={locked || editing} onClick={onCancel}>{busy ? '처리 중…' : '취소'}</button>
      </>}
      {actions === 'rejected' && <button type='button' disabled={locked || row.stale} onClick={onRestore}>{busy ? '처리 중…' : '되살리기'}</button>}
    </div>}
  </article>
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
  if (!row.starts_on && !row.ends_on) return '날짜 미기재'
  if (row.starts_on && row.ends_on) return `${row.starts_on} ~ ${row.ends_on}`
  return row.starts_on ? `시작 ${row.starts_on}` : `종료 ${row.ends_on}`
}

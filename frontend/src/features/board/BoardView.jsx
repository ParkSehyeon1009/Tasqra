import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createTask, deleteTask, listTasks, updateTask } from '../../api/task'
import PageHeading from '../../components/common/PageHeading'
import './BoardView.css'

const COLUMNS = [['TODO', '할 일'], ['IN_PROGRESS', '진행 중'], ['DONE', '완료']]
const TYPE_LABELS = { DEVELOPMENT: '개발', DESIGN: '디자인', INFRA: '인프라', DOCUMENT: '문서', OTHER: '기타' }

export default function BoardView({ projectId, members, canEdit, notify }) {
  const queryClient = useQueryClient()
  const tasksKey = ['projects', projectId, 'tasks']
  const tasksQuery = useQuery({ queryKey: tasksKey, queryFn: () => listTasks(projectId) })
  const [editingTask, setEditingTask] = useState(null)
  const [deletingTask, setDeletingTask] = useState(null)
  const [draggingTaskId, setDraggingTaskId] = useState(null)
  const [dragOverStatus, setDragOverStatus] = useState(null)
  const saveMutation = useMutation({
    mutationFn: values => editingTask?.id ? updateTask(projectId, editingTask.id, values) : createTask(projectId, values),
    onSuccess: saved => {
      queryClient.setQueryData(tasksKey, current => editingTask?.id ? current?.map(task => task.id === saved.id ? saved : task) : [saved, ...(current ?? [])])
      notify('success', editingTask?.id ? '태스크 수정 완료' : '태스크 생성 완료', `${saved.title} 태스크를 저장했습니다.`)
      setEditingTask(null)
    },
    onError: error => notify('error', '태스크 저장 실패', error.message),
  })
  const deleteMutation = useMutation({
    mutationFn: task => deleteTask(projectId, task.id),
    onSuccess: (_, task) => {
      queryClient.setQueryData(tasksKey, current => current?.filter(item => item.id !== task.id))
      notify('success', '태스크 삭제 완료', `${task.title} 태스크를 삭제했습니다.`)
      setDeletingTask(null)
    },
    onError: error => notify('error', '태스크 삭제 실패', error.message),
  })
  const statusMutation = useMutation({
    mutationFn: ({ task, status }) => updateTask(projectId, task.id, { status }),
    onMutate: async ({ task, status }) => {
      await queryClient.cancelQueries({ queryKey: tasksKey })
      const previous = queryClient.getQueryData(tasksKey)
      queryClient.setQueryData(tasksKey, current => current?.map(item => item.id === task.id ? { ...item, status } : item))
      return { previous }
    },
    onSuccess: saved => queryClient.setQueryData(tasksKey, current => current?.map(task => task.id === saved.id ? saved : task)),
    onError: (error, _, context) => {
      queryClient.setQueryData(tasksKey, context?.previous)
      notify('error', '태스크 이동 실패', error.message)
    },
    onSettled: () => { setDraggingTaskId(null); setDragOverStatus(null) },
  })
  const tasks = tasksQuery.data ?? []

  function startDragging(event, task) {
    if (!canEdit || statusMutation.isPending) { event.preventDefault(); return }
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(task.id))
    setDraggingTaskId(task.id)
  }
  function dropTask(event, status) {
    event.preventDefault()
    const taskId = Number(event.dataTransfer.getData('text/plain') || draggingTaskId)
    const task = tasks.find(item => item.id === taskId)
    setDragOverStatus(null)
    if (!task || task.status === status || statusMutation.isPending) { setDraggingTaskId(null); return }
    statusMutation.mutate({ task, status })
  }

  return <>
    <div className='task-board-heading'><PageHeading eyebrow='ACTION TASKS' title='액션 태스크' description='프로젝트에서 직접 등록한 작업을 상태별로 관리합니다.'/>{canEdit && <button className='primary' onClick={() => setEditingTask({})}>+ 태스크 만들기</button>}</div>
    {tasksQuery.isPending && <section className='board-empty-state' role='status'><div className='board-empty-icon'>…</div><div><h2>태스크를 불러오는 중입니다.</h2></div></section>}
    {tasksQuery.isError && <section className='board-empty-state board-error' role='alert'><div className='board-empty-icon'>!</div><div><h2>태스크를 불러오지 못했습니다.</h2><p>{tasksQuery.error.message}</p><button onClick={() => tasksQuery.refetch()}>다시 시도</button></div></section>}
    {tasksQuery.isSuccess && <div className='board task-board'>{COLUMNS.map(([status, label]) => {
      const columnTasks = tasks.filter(task => task.status === status)
      const activeDrop = canEdit && draggingTaskId && dragOverStatus === status
      return <section key={status} className={`task-column task-column-${status.toLowerCase()}${activeDrop ? ' is-drag-over' : ''}`} onDragOver={event => { if (canEdit) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; setDragOverStatus(status) } }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDragOverStatus(null) }} onDrop={event => dropTask(event, status)}><header><div><h2>{label}</h2><span>{columnTasks.length}</span></div></header>{columnTasks.length ? <div className='task-card-list'>{columnTasks.map(task => <TaskCard key={task.id} task={task} canEdit={canEdit} dragging={draggingTaskId === task.id} onDragStart={event => startDragging(event, task)} onDragEnd={() => { setDraggingTaskId(null); setDragOverStatus(null) }} onEdit={() => setEditingTask(task)} onDelete={() => setDeletingTask(task)}/>)}</div> : <p className='task-column-empty'>{activeDrop ? '여기에 놓아 상태를 변경합니다.' : '등록된 태스크가 없습니다.'}</p>}</section>
    })}</div>}
    {editingTask && <TaskDialog task={editingTask} members={members} pending={saveMutation.isPending} onClose={() => setEditingTask(null)} onSubmit={values => saveMutation.mutate(values)}/>}
    {deletingTask && <DeleteDialog task={deletingTask} pending={deleteMutation.isPending} onClose={() => setDeletingTask(null)} onDelete={() => deleteMutation.mutate(deletingTask)}/>}
  </>
}

function TaskCard({ task, canEdit, dragging, onDragStart, onDragEnd, onEdit, onDelete }) {
  return <article className={`task-board-card task-board-card-${task.type.toLowerCase()}${dragging ? ' is-dragging' : ''}`} draggable={canEdit} onDragStart={onDragStart} onDragEnd={onDragEnd}><div className='task-board-card-top'><span>{TYPE_LABELS[task.type] ?? '기타'}</span>{canEdit && <div><button onClick={onEdit}>수정</button><button className='danger-text' onClick={onDelete}>삭제</button></div>}</div><h3>{task.title}</h3>{task.description && <p>{task.description}</p>}<footer><span>{task.assignee?.name ?? '담당자 미정'}</span><time dateTime={task.due_on ?? undefined}>{task.due_on ? `~ ${task.due_on}` : '마감 미정'}</time></footer></article>
}

function TaskDialog({ task, members, pending, onClose, onSubmit }) {
  const now = new Date()
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const [title, setTitle] = useState(task.title ?? '')
  const [description, setDescription] = useState(task.description ?? '')
  const [type, setType] = useState(task.type ?? 'OTHER')
  const [status, setStatus] = useState(task.status ?? 'TODO')
  const [assigneeId, setAssigneeId] = useState(task.assignee?.id ? String(task.assignee.id) : '')
  const [dueOn, setDueOn] = useState(task.due_on ?? '')
  const [titleError, setTitleError] = useState('')
  function submit(event) {
    event.preventDefault()
    if (!title.trim()) { setTitleError('태스크 제목을 입력해 주세요.'); return }
    onSubmit({ title: title.trim(), description: description.trim() || null, type, status, assignee_id: assigneeId ? Number(assigneeId) : null, due_on: dueOn || null })
  }
  return <div className='dialog-backdrop' onMouseDown={event => event.target === event.currentTarget && !pending && onClose()}><form className='project-dialog task-dialog' onSubmit={submit} role='dialog' aria-modal='true' aria-labelledby='task-dialog-title'><header><div><p className='eyebrow'>ACTION TASK</p><h2 id='task-dialog-title'>{task.id ? '태스크 수정' : '새 태스크 만들기'}</h2></div><button type='button' className='dialog-close' onClick={onClose} disabled={pending}>×</button></header><label>제목<input autoFocus value={title} maxLength='300' aria-invalid={Boolean(titleError)} onChange={event => { setTitle(event.target.value); setTitleError('') }}/>{titleError && <small className='field-error'>{titleError}</small>}</label><label>설명<textarea rows='4' value={description} onChange={event => setDescription(event.target.value)}/></label><div className='task-dialog-grid'><label>유형<select value={type} onChange={event => setType(event.target.value)}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>상태<select value={status} onChange={event => setStatus(event.target.value)}>{COLUMNS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label></div><div className='task-dialog-grid'><label>담당자<select value={assigneeId} onChange={event => setAssigneeId(event.target.value)}><option value=''>담당자 미정</option>{members.map(member => <option key={member.user_id} value={member.user_id}>{member.name}</option>)}</select></label><label>마감일<input type='date' min={today} value={dueOn} onChange={event => setDueOn(event.target.value)}/></label></div><footer><button type='button' onClick={onClose} disabled={pending}>취소</button><button className='primary' disabled={pending}>{pending ? '저장 중...' : '저장'}</button></footer></form></div>
}

function DeleteDialog({ task, pending, onClose, onDelete }) {
  return <div className='dialog-backdrop'><section className='confirm-dialog' role='dialog' aria-modal='true' aria-labelledby='task-delete-title'><h2 id='task-delete-title'>태스크를 삭제할까요?</h2><p><strong>{task.title}</strong> 태스크가 삭제되며 되돌릴 수 없습니다.</p><div><button onClick={onClose} disabled={pending}>취소</button><button className='danger' onClick={onDelete} disabled={pending}>{pending ? '삭제 중...' : '삭제'}</button></div></section></div>
}

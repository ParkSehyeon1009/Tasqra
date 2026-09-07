const TYPE_LABELS = {
  DEVELOPMENT: '개발',
  DESIGN: '디자인',
  INFRA: '인프라',
  DOCUMENT: '문서',
}

const STATUS_LABELS = {
  TODO: '할 일',
  IN_PROGRESS: '진행 중',
  DONE: '완료',
}

export default function ActionTaskPanel({ tasks = [], loading = false, onOpenBoard }) {
  const openTasks = tasks.filter(task => task.status !== 'DONE').sort(compareTaskDeadline)
  const visibleTasks = openTasks.slice(0, 3)

  return <section className="panel dashboard-task-panel">
    <div className="panel-head"><div><h2>액션 태스크</h2><p>마감이 가까운 작업부터 표시합니다.</p></div><span>{openTasks.length}건</span></div>
    {visibleTasks.length ? <div className="dashboard-task-grid">{visibleTasks.map(task => <ActionTaskCard task={task} key={task.id}/>)}</div> : <div className="dashboard-task-empty"><strong>{loading ? '액션 태스크를 불러오는 중입니다.' : '열린 액션 태스크가 없습니다.'}</strong><p>{loading ? '잠시만 기다려 주세요.' : '보드에서 태스크를 만들거나 완료 상태를 확인하세요.'}</p></div>}
    <button className="dashboard-board-link" onClick={onOpenBoard}>전체 보드 보기 →</button>
  </section>
}

function compareTaskDeadline(left, right) {
  if (!left.due_on && !right.due_on) return Number(left.id ?? 0) - Number(right.id ?? 0)
  if (!left.due_on) return 1
  if (!right.due_on) return -1
  const byDate = left.due_on.localeCompare(right.due_on)
  return byDate || Number(left.id ?? 0) - Number(right.id ?? 0)
}

function ActionTaskCard({ task }) {
  const typeKey = TYPE_LABELS[task.type] ? task.type.toLowerCase() : 'default'
  const assignee = task.assignee?.name ?? task.assignee_name ?? '담당자 미정'
  const dueDate = task.due_on ? new Date(`${task.due_on}T00:00:00`).toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' }) : '마감 미정'
  const overdue = task.status !== 'DONE' && Boolean(task.due_on) && task.due_on < localTodayKey()

  return <article className={`dashboard-task-card task-type-${typeKey}`}>
    <div className="dashboard-task-card__top"><span className="dashboard-task-type">{TYPE_LABELS[task.type] ?? '기타'}</span><span className="dashboard-task-status">{STATUS_LABELS[task.status] ?? task.status}</span></div>
    <h3>{task.title}</h3>
    {task.description && <p title={task.description}>{task.description}</p>}
    <div className="dashboard-task-card__meta"><span>{assignee}</span><time className={overdue ? 'is-overdue' : undefined} dateTime={task.due_on ?? undefined} title={overdue ? '마감일이 지났습니다.' : undefined}>{dueDate}</time></div>
  </article>
}

function localTodayKey() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

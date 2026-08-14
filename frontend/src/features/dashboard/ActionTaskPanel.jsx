const TYPE_LABELS = {
  DEVELOPMENT: '개발',
  DESIGN: '디자인',
  INFRA: '인프라',
  DOCUMENT: '문서',
}

const STATUS_LABELS = {
  TODO: 'TODO',
  DOING: 'DOING',
  REVIEW: 'REVIEW',
  DONE: 'DONE',
}

export default function ActionTaskPanel({ tasks = [], onOpenBoard }) {
  const visibleTasks = tasks.filter(task => task.status !== 'DONE').slice(0, 4)

  return <section className="panel dashboard-task-panel">
    <div className="panel-head"><div><h2>액션 태스크</h2><p>보드에서 우선 처리할 작업입니다.</p></div><span>{visibleTasks.length}건</span></div>
    {visibleTasks.length ? <div className="dashboard-task-grid">{visibleTasks.map(task => <ActionTaskCard task={task} key={task.id}/>)}</div> : <div className="dashboard-task-empty"><strong>아직 등록된 액션 태스크가 없습니다.</strong><p>태스크 기능이 연결되면 우선 작업이 여기에 표시됩니다.</p></div>}
    <button className="dashboard-board-link" onClick={onOpenBoard}>전체 보드 보기 →</button>
  </section>
}

function ActionTaskCard({ task }) {
  const typeKey = TYPE_LABELS[task.type] ? task.type.toLowerCase() : 'default'
  const assignee = task.assignee?.name ?? task.assignee_name ?? '담당자 미정'
  const dueDate = task.due_at ? new Date(task.due_at).toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' }) : '마감 미정'

  return <article className={`dashboard-task-card task-type-${typeKey}`}>
    <div className="dashboard-task-card__top"><span className="dashboard-task-type">{TYPE_LABELS[task.type] ?? '기타'}</span><span className="dashboard-task-status">{STATUS_LABELS[task.status] ?? task.status}</span></div>
    <h3>{task.title}</h3>
    {task.description && <p>{task.description}</p>}
    <div className="dashboard-task-card__meta"><span>{assignee}</span><time dateTime={task.due_at ?? undefined}>{dueDate}</time></div>
  </article>
}

// =============================================================================
// 이 파일의 책임: 프로젝트 태스크 마감과 승인된 일정을 월간 달력으로 보여주고,
//   선택한 날짜의 항목을 우측 목록에 표시한다.
// 다른 파일과의 관계: api/dashboard.js로 통합 조회한다. 우측 목록의 태스크를
//   누르면 BoardView의 기존 task_id 상세 흐름으로 이동하고, 일정은 여기서 읽는다.
// Spring 비교: 서버 DTO를 월간 달력 ViewModel로 표현하는 읽기 전용 MVC View다.
// =============================================================================

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getDashboardCalendar } from '../../api/dashboard'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']
const KIND_LABELS = {
  TASK_DUE: '태스크 마감',
  MEETING: '회의',
  MILESTONE: '주요 시점',
  DEADLINE: '외부 기한',
  PERIOD: '기간',
}
const TASK_STATUS_LABELS = { TODO: '할 일', IN_PROGRESS: '진행 중', DONE: '완료' }
const TASK_TYPE_LABELS = { DEVELOPMENT: '개발', DESIGN: '디자인', INFRA: '인프라', DOCUMENT: '문서', OTHER: '기타' }

export default function ProjectCalendar({ projectId, tasks }) {
  const navigate = useNavigate()
  const [month, setMonth] = useState(() => startOfMonth(new Date()))
  const [selectedDate, setSelectedDate] = useState(() => toDateKey(new Date()))
  const [selectedSchedule, setSelectedSchedule] = useState(null)
  const days = useMemo(() => calendarDays(month), [month])
  const from = toDateKey(days[0])
  const to = toDateKey(days.at(-1))
  const calendarQuery = useQuery({
    queryKey: ['projects', projectId, 'calendar', from, to],
    queryFn: () => getDashboardCalendar(projectId, { from, to }),
  })
  const items = calendarQuery.data?.items ?? []
  const selectedItems = items.filter(item => occursOn(item, selectedDate))
  const monthStart = toDateKey(startOfMonth(month))
  const monthEnd = toDateKey(new Date(month.getFullYear(), month.getMonth() + 1, 0))
  const hasMonthItems = items.some(item => overlaps(item, monthStart, monthEnd))

  function moveMonth(offset) {
    const next = new Date(month.getFullYear(), month.getMonth() + offset, 1)
    setMonth(next)
    selectDate(toDateKey(next))
  }
  function goToday() {
    const today = new Date()
    setMonth(startOfMonth(today))
    selectDate(toDateKey(today))
  }
  function selectDate(dateKey) {
    setSelectedDate(dateKey)
    setSelectedSchedule(null)
  }
  function openListItem(item) {
    if (item.item_type === 'TASK') {
      navigate(`/projects/${projectId}/board?task_id=${item.source_id}`)
      return
    }
    setSelectedSchedule(item)
  }

  return <section className='panel project-calendar' aria-labelledby='project-calendar-title'>
    <div className='project-calendar__head'>
      <div><h2 id='project-calendar-title'>프로젝트 캘린더</h2><p>날짜를 선택하면 태스크 마감과 승인된 일정을 확인할 수 있습니다.</p></div>
      <div className='project-calendar__controls'>
        <button type='button' onClick={() => moveMonth(-1)} aria-label='이전 달'>‹</button>
        <strong aria-live='polite'>{month.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long' })}</strong>
        <button type='button' onClick={() => moveMonth(1)} aria-label='다음 달'>›</button>
        <button type='button' className='project-calendar__today' onClick={goToday}>오늘</button>
      </div>
    </div>

    {calendarQuery.isError && <div className='project-calendar__notice' role='alert'><span><strong>캘린더를 불러오지 못했습니다.</strong><small>{calendarQuery.error?.message}</small></span><button type='button' onClick={() => calendarQuery.refetch()}>다시 시도</button></div>}

    <div className='project-calendar__layout'>
      <div className='project-calendar__month' aria-busy={calendarQuery.isPending}>
        <div className='project-calendar__weekdays' aria-hidden='true'>{WEEKDAYS.map((day, index) => <span className={index === 0 ? 'is-sunday' : undefined} key={day}>{day}</span>)}</div>
        <div className='project-calendar__grid'>
          {days.map(day => {
            const dateKey = toDateKey(day)
            const dayItems = items.filter(item => occursOn(item, dateKey)).sort(calendarItemOrder)
            const preview = dayItems[0]
            const outside = day.getMonth() !== month.getMonth()
            const selected = dateKey === selectedDate
            const today = dateKey === toDateKey(new Date())
            const sunday = day.getDay() === 0
            return <div className={`project-calendar__day${outside ? ' is-outside' : ''}${selected ? ' is-selected' : ''}${today ? ' is-today' : ''}${sunday ? ' is-sunday' : ''}`} key={dateKey}>
              <button type='button' className='project-calendar__date' aria-pressed={selected} onClick={() => selectDate(dateKey)}><span>{day.getDate()}</span>{today && <small>오늘</small>}</button>
              <div className='project-calendar__events'>
                {preview && <button type='button' className={calendarEventClass(preview, dateKey, day, tasks)} aria-label={`${calendarItemLabel(preview, tasks)} ${preview.title}, ${formatDate(dateKey)} 항목 보기`} onClick={() => selectDate(dateKey)}><span>{calendarItemLabel(preview, tasks)}</span><b>{showEventTitle(preview, dateKey, day) ? preview.title : '\u00a0'}</b></button>}
                {dayItems.length > 1 && <button type='button' className='project-calendar__more' onClick={() => selectDate(dateKey)}>+{dayItems.length - 1}개 더 보기</button>}
              </div>
            </div>
          })}
        </div>
        {calendarQuery.isPending && <div className='project-calendar__loading' role='status'>캘린더를 불러오는 중입니다.</div>}
        {calendarQuery.isSuccess && !hasMonthItems && <p className='project-calendar__month-empty'>이 달에 표시할 태스크 마감이나 승인된 일정이 없습니다.</p>}
      </div>

      <aside className={`project-calendar__detail${selectedSchedule ? ' is-open' : ''}`} aria-label='선택한 날짜의 항목'>
        {selectedSchedule
          ? <>
              <header><span>일정 상세</span><button type='button' className='project-calendar__detail-close' onClick={() => setSelectedSchedule(null)} aria-label='일정 상세 닫기'>×</button></header>
              <ScheduleDetail item={selectedSchedule}/>
            </>
          : <>
              <header><span>{formatDate(selectedDate)}</span><strong>{selectedItems.length}개 항목</strong></header>
              {selectedItems.length > 0
                ? <ul>{selectedItems.map(item => <li key={item.id}><button type='button' className={calendarItemToneClass(item, tasks)} onClick={() => openListItem(item)}><span>{item.item_type === 'TASK' ? `태스크 · ${calendarItemLabel(item, tasks)}` : `일정 · ${KIND_LABELS[item.kind] ?? item.kind}`}</span><strong>{item.title}</strong><small>{item.item_type === 'TASK' ? `${TASK_STATUS_LABELS[item.status] ?? item.status} · 보드에서 상세 보기 →` : formatEventDate(item)}</small></button></li>)}</ul>
                : <div className='project-calendar__empty'><strong>이 날짜에는 항목이 없습니다.</strong><p>마감일이 있는 태스크나 승인된 일정이 생기면 자동으로 표시됩니다.</p></div>}
            </>}
      </aside>
    </div>
  </section>
}

function ScheduleDetail({ item }) {
  return <div className={`project-calendar__schedule-detail kind-${item.kind.toLowerCase()}`}>
    <span>일정 · {KIND_LABELS[item.kind] ?? item.kind}</span>
    <h3>{item.title}</h3>
    <dl><div><dt>날짜</dt><dd>{formatEventDate(item)}</dd></div><div><dt>상태</dt><dd>승인 완료</dd></div></dl>
  </div>
}

function startOfMonth(value) {
  return new Date(value.getFullYear(), value.getMonth(), 1)
}

function calendarDays(month) {
  const first = startOfMonth(month)
  const firstCell = new Date(first.getFullYear(), first.getMonth(), 1 - first.getDay())
  return Array.from({ length: 42 }, (_, index) => new Date(firstCell.getFullYear(), firstCell.getMonth(), firstCell.getDate() + index))
}

function toDateKey(value) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`
}

function eventPrimaryDate(item) {
  return item.kind === 'DEADLINE' ? item.ends_on : item.starts_on
}

function occursOn(item, dateKey) {
  if (item.kind === 'PERIOD') return Boolean(item.starts_on && item.ends_on && item.starts_on <= dateKey && dateKey <= item.ends_on)
  return eventPrimaryDate(item) === dateKey
}

function overlaps(item, startsOn, endsOn) {
  if (item.kind === 'PERIOD') return Boolean(item.starts_on && item.ends_on && item.starts_on <= endsOn && item.ends_on >= startsOn)
  const date = eventPrimaryDate(item)
  return Boolean(date && startsOn <= date && date <= endsOn)
}

function calendarItemOrder(left, right) {
  if (left.kind === 'PERIOD' && right.kind !== 'PERIOD') return -1
  if (left.kind !== 'PERIOD' && right.kind === 'PERIOD') return 1
  return left.id.localeCompare(right.id)
}

function calendarItemToneClass(item, tasks) {
  if (item.item_type !== 'TASK') return `kind-${item.kind.toLowerCase()}`
  const type = tasks.find(task => task.id === item.source_id)?.type ?? 'OTHER'
  return `task-type-${type.toLowerCase()}`
}

function calendarItemLabel(item, tasks) {
  if (item.item_type !== 'TASK') return KIND_LABELS[item.kind] ?? item.kind
  const type = tasks.find(task => task.id === item.source_id)?.type ?? 'OTHER'
  return `${TASK_TYPE_LABELS[type] ?? TASK_TYPE_LABELS.OTHER} · 마감`
}

function calendarEventClass(item, dateKey, day, tasks) {
  const classes = ['project-calendar__event', calendarItemToneClass(item, tasks)]
  if (item.kind !== 'PERIOD') return classes.join(' ')
  classes.push('is-period')
  if (item.starts_on === dateKey || day.getDay() === 0) classes.push('is-period-start')
  if (item.ends_on === dateKey || day.getDay() === 6) classes.push('is-period-end')
  return classes.join(' ')
}

function showEventTitle(item, dateKey, day) {
  return item.kind !== 'PERIOD' || item.starts_on === dateKey || day.getDay() === 0
}

function formatDate(dateKey) {
  const [year, month, day] = dateKey.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' })
}

function formatEventDate(item) {
  if (item.kind === 'PERIOD') return `${item.starts_on} ~ ${item.ends_on}`
  return eventPrimaryDate(item) ?? '날짜 미정'
}

// =============================================================================
// 이 파일의 책임: 산출물 조건 선택(DLV-001-1)과 생성 대상 미리보기
//   (DLV-001-2) 화면이다. 유형·기간·출력 형식을 고르고, 담길 내용이 몇 건인지
//   확인한 뒤 조건이 빠졌거나 담을 것이 없으면 생성을 막는다.
// 다른 파일과의 관계: api/deliverable.js 로 건수를 받는다. 표기 규칙은
//   utils/format.js 를 쓴다. WorkspacePage 의 '산출물' 탭에서 그린다.
// Spring 비교: 서버가 만든 뷰 모델을 그대로 그리는 화면이다. 판단을 화면에서
//   다시 하지 않는다.
//
// 완료 판정이 이 화면의 모양을 정했다
//   DLV-001-2: "**LLM 호출 전에 건수가 보이고** 대상이 없으면 생성이 방지된다"
//   그래서 ① 건수가 보이는 것과 ② 막히는 것이 둘 다 화면에 있어야 한다.
//   막히는 것은 비활성 버튼과 그 아래 이유 문장으로 드러낸다.
//
// 판단을 화면에서 다시 하지 않는다
//   can_generate 를 건수로 계산하지 않고 서버 값을 그대로 쓴다. 승인 대기는
//   건수에 있지만 생성 가능 판정에는 더하지 않는다 같은 규칙이 섞여 있어서,
//   화면에서 다시 구현하면 조용히 어긋난다.
//
//   같은 이유로 **"담길 내용 합계" 를 보여주지 않는다.** 합계를 내려면 어느 넷을
//   더하는지 화면이 알아야 하는데 그것이 곧 규칙 복제다(서버는 합계를 응답에
//   담지 않는다 — countable_total 은 내부 판단용 프로퍼티다). 합계 대신
//   카드를 "담길 내용" 과 "담기지 않는 것" 으로 묶어서 뜻을 드러낸다.
//
// 기간 입력을 유형과 무관하게 늘 띄우는 이유
//   어느 유형이 기간을 쓰는지는 서버가 안다(주간 보고서만 필수). 화면이 그것을
//   알아야 한다면 그 규칙이 DB CHECK · 서비스 · 화면 세 곳에 생긴다. 그래서
//   기간은 늘 보내고, 쓰지 않는 유형에서는 서버가 무시한다. 응답의 needs_period
//   로 "이 유형은 기간을 쓰지 않는다" 는 안내만 띄운다.
//   기본값을 이번 주로 넣어 두므로 주간 보고서에서도 처음부터 값이 있다.
// =============================================================================

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createDeliverable,
  deleteDeliverable,
  downloadDeliverable,
  getDeliverableContent,
  getDeliverablePreview,
  listDeliverables,
} from '../../api/deliverable'
import ConfirmDialog from '../../components/common/ConfirmDialog'
import PageHeading from '../../components/common/PageHeading'
import { formatDateTime, formatNumber } from '../../utils/format'
import './DeliverablesView.css'

// 산출물 유형. 값은 서버의 DELIVERABLE_KINDS 와 같아야 한다(리비전 0007 의
// CHECK 가 근거다). 여기 있는 것은 **표시 문구뿐**이고 기간 규칙은 담지 않는다.
//
// "담기는 것" 설명을 화면에 두는 이유: 유형마다 세는 대상이 다른데 그것을 모르면
// 결정사항 대장에서 기간을 바꿔도 숫자가 안 변하는 것이 고장처럼 보인다.
const KINDS = [
  ['WEEKLY_REPORT', '주간 보고서', '기간 안의 문서·결정·일정·금액'],
  ['DECISION_LOG', '결정사항 대장', '결정 전부 (확정·미결·뒤집힘)'],
  ['MEETING_AGENDA', '다음 회의 안건', '아직 정해지지 않은 결정만'],
  ['PROJECT_STATUS', '프로젝트 현황', '지금 상태 전부'],
]

// 출력 형식. 값은 Deliverable 모델의 ck_deliverable_format CHECK 와 같아야 한다.
// 리비전 0021 이 그 CHECK 를 XLSX·HTML·MD·PDF 넷으로 넓혔으므로 화면도 넷을 준다 —
// DB 가 받는 형식이 화면에 없으면 사용자는 그 형식을 고를 방법이 없다.
// 기본 선택을 두지 않는다 — DLV-001-1 완료 판정이 "형식을 고르지 않으면 생성
// 버튼이 비활성화된다" 이므로, 사용자가 한 번 명시적으로 골라야 한다.
//
// 네 번째 칸(ready)은 **지금 실제로 만들 수 있는지**다. 서버의
// SUPPORTED_DELIVERABLE_FORMATS 가 MD·HTML 둘뿐이고 나머지는
// 501 DELIVERABLE_FORMAT_NOT_READY 로 답한다.
//
// 숨기지 않고 고를 수 없게만 두는 이유
//   숨기면 DB·명세에 있는 형식이 화면에서 사라져 "안 되는 것" 인지 "없는 것" 인지
//   구분되지 않는다. 반대로 그냥 누르게 두면 501 을 받고 나서야 알게 되는데,
//   사용자에게는 그것이 **고장으로 읽힌다.** 그래서 **누르기 전에** 준비 중임이
//   보이게 한다. 서버의 501 은 그대로 남는다 — 화면을 우회해도 막힌다.
const FORMATS = [
  ['XLSX', 'XLSX', '표 계산과 편집에 적합', false],
  ['HTML', 'HTML', '브라우저에서 바로 확인', true],
  ['MD', 'Markdown', '텍스트 기반 기록과 공유', true],
  ['PDF', 'PDF', '그대로 인쇄하고 공유', false],
]

// 산출물에 실제로 담기는 재료. 순서는 명세가 나열한 순서다 —
// "문서·태스크·결정·기한·금액"(DLV-001-2).
//
// 완료한 태스크가 여기로 올라온 이유
//   전에는 "담기지 않는 것" 에 있었다. tasks 테이블이 없어 셀 수 없었기 때문이다
//   (응답이 null 이었다). 리비전 0019 로 테이블이 생겨 이제 실제로 세고, 주간
//   보고서의 재료이므로 담길 내용에 둔다.
const CONTENT_COUNTS = [
  ['documents', '문서'],
  ['completed_tasks', '완료한 태스크'],
  ['decisions', '결정사항'],
  ['schedule_items', '일정'],
  ['amount_items', '금액 항목'],
]

// 건수는 보여주지만 산출물에 담기지 않는 것. 왜 담기지 않는지를 note 로 적는다 —
// 적지 않으면 "4건이 있는데 왜 못 만드나" 가 된다.
const ASIDE_COUNTS = [
  ['pending_suggestions', '승인 대기', '승인하면 담깁니다'],
]

/** Date 를 'YYYY-MM-DD' 로. toISOString() 을 쓰지 않는다 — 그것은 UTC 라서
 *  한국 시간 09시 이전에는 날짜가 하루 앞으로 밀린다. */
function toDateInput(date) {
  const pad = number => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 이번 주 월요일~일요일. 주간 보고서의 기본 기간이다. */
function thisWeek() {
  const today = new Date()
  const monday = new Date(today)
  // getDay() 는 일요일이 0 이다. 월요일을 주의 시작으로 삼아 옮긴다.
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return [toDateInput(monday), toDateInput(sunday)]
}

const [DEFAULT_FROM, DEFAULT_TO] = thisWeek()

export default function DeliverablesView({ projectId, notify }) {
  const [kind, setKind] = useState('WEEKLY_REPORT')
  // 기본값 없음. 사용자가 출력 형식을 명시적으로 골라야 한다(DLV-001-1).
  const [format, setFormat] = useState('')
  const [periodFrom, setPeriodFrom] = useState(DEFAULT_FROM)
  const [periodTo, setPeriodTo] = useState(DEFAULT_TO)
  // 삭제 확인 대상. null 이면 확인창이 닫혀 있다.
  const [deleteTarget, setDeleteTarget] = useState(null)
  // 본문 미리보기를 펼쳤는가. **닫혀 있으면 부르지 않는다** — 합계만 보려고 들어온
  // 사람에게 문서를 조립하는 비용을 물릴 이유가 없다.
  const [contentOpen, setContentOpen] = useState(false)
  const queryClient = useQueryClient()

  const previewQuery = useQuery({
    queryKey: ['projects', projectId, 'deliverable-preview', kind, periodFrom, periodTo],
    queryFn: () => getDeliverablePreview(projectId, { kind, periodFrom, periodTo }),
    // 날짜가 비어 있으면 부르지 않는다. 주간 보고서에서 422 가 날 뿐이다.
    enabled: Boolean(periodFrom && periodTo),
    // 시작일이 종료일보다 늦은 경우는 **서버가 판정한다**(422
    // INVALID_PROJECT_DATES). 화면에서 미리 막으면 같은 규칙이 두 곳에 생긴다.
    retry: false,
  })
  const preview = previewQuery.data
  const counts = preview?.counts
  // 어느 항목을 셀 수 없는지 서버가 알려준다. 화면이 필드 이름을 외우지 않는다.
  const uncountable = preview?.uncountable ?? []
  const selected = KINDS.find(([value]) => value === kind)

  // 생성 이력(DLV-003-3). 조건과 무관하므로 kind·기간을 키에 넣지 않는다 —
  // 넣으면 유형을 바꿀 때마다 목록이 비었다가 다시 채워진다.
  const historyQuery = useQuery({
    queryKey: ['projects', projectId, 'deliverables'],
    queryFn: () => listDeliverables(projectId),
    retry: false,
  })

  const createMutation = useMutation({
    mutationFn: () => createDeliverable(projectId, { kind, format, periodFrom, periodTo }),
    onSuccess: created => {
      notify?.('success', '산출물을 만들었습니다', `${created.title} · ${created.format}`)
      // 이력을 다시 받는다. 미리보기도 함께 — 방금 만든 것이 최신인지 판정하는
      // 기준이 이 시각이므로, 다른 화면에서 돌아왔을 때 낡은 값을 쓰지 않게 한다.
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'deliverables'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'deliverable-preview'] })
    },
    // 서버 문구를 그대로 보여준다. 422 DELIVERABLE_EMPTY 든 501 이든 이미 사용자가
    // 읽을 수 있는 한국어다. 화면이 code 별로 문장을 다시 만들면 서버와 어긋난다.
    onError: error => notify?.('error', '산출물을 만들지 못했습니다', error?.message),
  })

  const downloadMutation = useMutation({
    mutationFn: item => downloadDeliverable(item.download_url, `${item.title}.${item.format.toLowerCase()}`),
    onError: error => notify?.('error', '내려받지 못했습니다', error?.message),
  })

  const deleteMutation = useMutation({
    mutationFn: item => deleteDeliverable(projectId, item.id),
    onSuccess: () => {
      notify?.('success', '산출물을 삭제했습니다', '이력과 파일이 함께 지워졌습니다.')
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'deliverables'] })
    },
    onError: error => notify?.('error', '삭제하지 못했습니다', error?.message),
    onSettled: () => setDeleteTarget(null),
  })

  return <>
    <PageHeading
      eyebrow='DELIVERABLES'
      title='산출물'
      description='만들기 전에 담길 내용이 몇 건인지 확인하세요. 담을 것이 없으면 생성되지 않습니다.'
    />

    <section className='panel deliverable-controls' aria-label='산출물 조건'>
      <div className='deliverable-kind-group' role='group' aria-label='산출물 유형'>
        {KINDS.map(([value, label, contains]) => <button
          className={'deliverable-kind' + (value === kind ? ' is-active' : '')}
          type='button'
          key={value}
          aria-pressed={value === kind}
          onClick={() => setKind(value)}
        ><strong>{label}</strong><span>{contains}</span></button>)}
      </div>

      <div className='deliverable-period'>
        <label>
          <span>시작일</span>
          <input type='date' value={periodFrom} max={periodTo} onChange={event => setPeriodFrom(event.target.value)}/>
        </label>
        <label>
          <span>종료일</span>
          <input type='date' value={periodTo} min={periodFrom} onChange={event => setPeriodTo(event.target.value)}/>
        </label>
        {/* needs_period 는 서버가 정한다. 응답이 오기 전에는 아무 말도 하지 않는다 —
            추측해서 안내하면 유형을 바꾼 직후 잘못된 문구가 잠깐 보인다. */}
        {preview && !preview.needs_period && <p className='deliverable-period-note'>
          <strong>{selected?.[1]}</strong>은 기간을 쓰지 않습니다. 날짜를 바꿔도 결과가 같습니다.
        </p>}
      </div>

      <div className='deliverable-format-fieldset'>
        <div className='deliverable-control-heading'>
          <strong>출력 형식</strong>
          <span>하나를 선택해야 만들 수 있습니다.</span>
        </div>
        <div className='deliverable-format-group' role='group' aria-label='출력 형식'>
          {FORMATS.map(([value, label, description, ready]) => <button
            className={'deliverable-format' + (value === format ? ' is-active' : '') + (ready ? '' : ' is-unready')}
            type='button'
            key={value}
            aria-pressed={value === format}
            disabled={!ready}
            onClick={() => setFormat(value)}
          ><strong>{label}</strong><span>{ready ? description : '아직 만들 수 없습니다'}</span></button>)}
        </div>
      </div>
    </section>

    {previewQuery.isError && <section className='panel deliverable-notice'>
      <div>
        <strong>담길 내용을 불러오지 못했습니다.</strong>
        <p>{previewQuery.error?.message}</p>
      </div>
      <button type='button' onClick={() => previewQuery.refetch()}>다시 시도</button>
    </section>}

    <section className='deliverable-count-grid' aria-label='담길 내용'>
      <h2 className='deliverable-group-heading'>담길 내용</h2>
      {CONTENT_COUNTS.map(([key, label]) => <CountCard
        key={key}
        label={label}
        value={counts?.[key]}
        unknown={uncountable.includes(key)}
      />)}
    </section>

    <section className='deliverable-count-grid deliverable-count-grid--aside' aria-label='담기지 않는 것'>
      <h2 className='deliverable-group-heading'>담기지 않는 것</h2>
      {ASIDE_COUNTS.map(([key, label, note]) => <CountCard
        key={key}
        label={label}
        value={counts?.[key]}
        note={note}
        unknown={uncountable.includes(key)}
      />)}
    </section>

    <GeneratePanel
      preview={preview}
      loading={previewQuery.isPending}
      format={format}
      generating={createMutation.isPending}
      onGenerate={() => createMutation.mutate()}
      contentOpen={contentOpen}
      onToggleContent={() => setContentOpen(current => !current)}
    />

    {contentOpen && <ContentPreview
      projectId={projectId}
      kind={kind}
      format={format}
      periodFrom={periodFrom}
      periodTo={periodTo}
    />}

    <HistoryPanel
      query={historyQuery}
      downloadingId={downloadMutation.isPending ? downloadMutation.variables?.id : null}
      onDownload={item => downloadMutation.mutate(item)}
      onDelete={item => setDeleteTarget(item)}
    />

    <ConfirmDialog
      open={Boolean(deleteTarget)}
      title='산출물을 삭제할까요?'
      message={`${deleteTarget?.title ?? ''} (${deleteTarget?.format ?? ''}) 의 이력과 파일이 함께 지워집니다. 같은 조건으로 다시 만들 수 있습니다.`}
      confirmLabel='삭제'
      danger
      onCancel={() => setDeleteTarget(null)}
      onConfirm={() => deleteMutation.mutate(deleteTarget)}
    />
  </>
}

// 값이 null·undefined 면 '—' 를 보여준다. 0 과 구별하기 위한 것이다.
//   0    — 실제로 0건이다
//   —    — 아직 못 받았거나(로딩) 셀 수 없다(응답의 uncountable 에 있는 재료)
// 둘을 같은 '—' 로 두되 **셀 수 없는 것에는 이유를 적는다.** 대시보드의
// SummaryCard 와 같은 규칙이다. 0 으로 바꾸면 사용자가 "없다" 로 잘못 읽는다.
function CountCard({ label, value, note, unknown }) {
  const shown = value === null || value === undefined ? '—' : formatNumber(value)
  return <section className={'deliverable-count-card' + (unknown ? ' is-unknown' : '')}>
    <span>{label}</span>
    <strong>{shown}{value === null || value === undefined ? '' : '건'}</strong>
    {unknown ? <p>아직 집계할 수 없습니다 (태스크 기능 준비 중)</p> : note && <p>{note}</p>}
  </section>
}

// 생성 영역. **막히는 것이 보이는 자리**라서 화면에서 가장 중요하다.
//
// `format` 은 서버 미리보기와 무관한 **사용자 입력 조건**이다. can_generate 는
// 담을 내용이 있는지만 판단하므로, 화면이 형식 누락을 별도로 막아야 한다.
// 기본값을 두지 않아 사용자가 한 번 명시적으로 고르게 한다(DLV-001-1).
//
// 막는 이유를 버튼이 아니라 **문장으로** 적는다. 비활성 버튼만 있으면 왜 못
// 누르는지 알 수 없어서, 사용자는 조건을 이리저리 바꿔 보게 된다.
function GeneratePanel({ preview, loading, format, generating, onGenerate, contentOpen, onToggleContent }) {
  const contentBlocked = preview ? !preview.can_generate : true
  const formatMissing = !format
  const disabled = loading || contentBlocked || formatMissing || generating
  return <section className='panel deliverable-generate'>
    <div>
      <h2>산출물 만들기</h2>
      {loading
        ? <p>담길 내용을 확인하는 중입니다.</p>
        : formatMissing
          ? <p className='deliverable-blocked'>출력 형식을 선택해야 만들 수 있습니다.</p>
          : contentBlocked
            ? <p className='deliverable-blocked'>{preview?.blocked_reason ?? '담길 내용을 확인한 뒤 만들 수 있습니다.'}</p>
            : <p>담길 내용이 있습니다. <strong>{format}</strong> 형식으로 만들 수 있습니다.</p>}
      <p className='deliverable-generate-note'>만든 산출물은 아래 <strong>만든 산출물</strong> 목록에 쌓입니다. 개요 문장은 아직 들어가지 않습니다.</p>
    </div>
    <div className='deliverable-generate-actions'>
      {/* 미리보기는 **형식을 안 골라도** 된다. 형식과 무관하게 담길 내용이 같기
          때문이다. 담을 것이 없을 때만 막는다 — 그때는 서버도 422 로 막는다. */}
      <button
        type='button'
        className='deliverable-preview-button'
        aria-expanded={contentOpen}
        disabled={loading || contentBlocked}
        onClick={onToggleContent}
      >{contentOpen ? '미리보기 닫기' : '미리보기'}</button>
      <button
        type='button'
        className='deliverable-generate-button'
        disabled={disabled}
        onClick={onGenerate}
      >{generating ? '만드는 중…' : '만들기'}</button>
    </div>
  </section>
}

// 미리보기에서 고를 수 있는 보기 방식.
//
// 「그대로 보기」는 실제 파일 모양이고 「글자로 보기」는 마크다운 원문이다. 둘 다
// 두는 이유: HTML 은 결과를 보여주지만 MD 는 **어떤 표가 어떻게 적히는지**를 보여준다.
// 산출물을 다른 문서에 붙여 쓸 사람에게는 뒤쪽이 필요하다.
//
// XLSX·PDF 는 서버가 501 로 막으므로 여기 두지 않는다 — 고를 수 있게 해 두면
// 미리보기만 되고 만들기는 안 되는 것처럼 보인다.
const PREVIEW_VIEWS = [
  ['HTML', '그대로 보기'],
  ['MD', '글자로 보기'],
]

// 본문 미리보기. **만들지 않고** 서버가 조립한 본문을 보여준다.
//
// 조건(유형·기간·보기 방식)을 바꾸면 다시 받는다 — queryKey 에 넣어 뒀다. 그래서
// 조건을 바꿔가며 결과를 나란히 볼 수 있다. 새 창으로 띄우면 그게 안 된다.
//
// **HTML 을 iframe sandbox 안에서 그린다.** dangerouslySetInnerHTML 로 심지 않는다.
// 서버가 모든 값을 html.escape 하지만, 그 한 겹만 믿고 심으면 나중에 절을 더하는
// 사람이 escape 를 빠뜨렸을 때 바로 XSS 가 된다. sandbox 는 스크립트·폼·부모 접근을
// 모두 막아서 그런 실수를 실행 불가능하게 만든다.
//
// 나중에 형식이 늘어날 때
//   PDF  — 같은 iframe 에 blob URL 을 넣으면 브라우저가 그려 준다
//   XLSX — 브라우저가 못 그린다. 그런데 **HTML 렌더로 대신할 수 있다** — 두 형식이
//          같은 build_document 에서 나오므로 담긴 내용이 같다
function ContentPreview({ projectId, kind, format, periodFrom, periodTo }) {
  // 만들 형식을 골라 뒀으면 그것으로 시작한다. 안 골랐으면 눈으로 보기 좋은 HTML.
  const [view, setView] = useState(format === 'MD' ? 'MD' : 'HTML')
  const [tall, setTall] = useState(false)
  const contentQuery = useQuery({
    queryKey: ['projects', projectId, 'deliverable-content', kind, view, periodFrom, periodTo],
    queryFn: () => getDeliverableContent(projectId, { kind, format: view, periodFrom, periodTo }),
    enabled: Boolean(periodFrom && periodTo),
    retry: false,
  })
  const data = contentQuery.data

  return <section className='panel deliverable-content' aria-label='산출물 미리보기'>
    <div className='deliverable-content-heading'>
      <h2>{data?.title ?? '미리보기'}</h2>
      <span>아직 만들지 않았습니다. 이력에도 남지 않습니다.</span>
    </div>

    <div className='deliverable-content-tools'>
      <div className='deliverable-content-views' role='group' aria-label='보기 방식'>
        {PREVIEW_VIEWS.map(([value, label]) => <button
          className={'deliverable-content-view' + (value === view ? ' is-active' : '')}
          type='button'
          key={value}
          aria-pressed={value === view}
          onClick={() => setView(value)}
        >{label}</button>)}
      </div>
      <button type='button' className='deliverable-content-view' onClick={() => setTall(current => !current)}>
        {tall ? '작게' : '크게 보기'}
      </button>
    </div>

    {contentQuery.isPending
      ? <p className='deliverable-content-empty'>본문을 만드는 중입니다.</p>
      : contentQuery.isError
        ? <p className='deliverable-content-empty'>미리보기를 만들지 못했습니다. {contentQuery.error?.message}</p>
        : view === 'HTML'
          // sandbox 를 빈 값으로 둔다 = 가장 강한 제한(스크립트·폼·팝업·부모 접근 모두 차단).
          // 허용 항목을 하나라도 더하면 그만큼 열리므로, 필요해질 때까지 비워 둔다.
          ? <iframe
            className={'deliverable-content-frame' + (tall ? ' is-tall' : '')}
            sandbox=''
            srcDoc={data.body}
            title={`${data.title} 미리보기`}
          />
          : <pre className={'deliverable-content-body' + (tall ? ' is-tall' : '')}>{data.body}</pre>}

    <p className='deliverable-content-note'>
      <strong>담길 내용은 형식과 무관하게 같습니다</strong> — 절을 고르는 규칙이 하나입니다.
      모양만 달라집니다. <strong>XLSX·PDF</strong> 는 아직 만들 수 없어 미리보기에도 없습니다.
    </p>
  </section>
}

// 재료 이름 → 화면 문구. CONTENT_COUNTS 에서 그대로 만든다.
//
// 라벨을 다시 적지 않는 이유: '완료한 태스크' 같은 문구가 두 곳에 생기면 한쪽만
// 고쳐서 같은 화면에서 이름이 달라진다. 서버의 stale_changes 키는 미리보기 counts
// 와 같은 키를 쓰므로 이 표 하나로 덮인다.
const MATERIAL_LABELS = Object.fromEntries(CONTENT_COUNTS)

/** 늘어난 재료를 한국어 문장으로. `{documents: 2}` → `문서 2건` */
function staleSentence(changes) {
  return Object.entries(changes ?? {})
    .map(([key, added]) => `${MATERIAL_LABELS[key] ?? key} ${formatNumber(added)}건`)
    .join(' · ')
}

/** 파일 크기. 산출물은 문서 파일보다 훨씬 작아서 KB 까지만 보인다. */
function formatFileSize(bytes) {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes < 1024) return `${formatNumber(bytes)} B`
  return `${formatNumber(Math.round(bytes / 1024))} KB`
}

// 생성 이력(DLV-003-3)과 갱신 필요 표시(DLV-003-4).
//
// 목록이 비어 있을 때 "없습니다" 만 적지 않는다. 이 화면에 처음 온 사용자는 위쪽
// 만들기와 이 목록이 이어진다는 것을 모른다 — 그래서 무엇을 하면 채워지는지 적는다.
function HistoryPanel({ query, downloadingId, onDownload, onDelete }) {
  const items = query.data ?? []
  return <section className='panel deliverable-history' aria-label='만든 산출물'>
    <div className='deliverable-history-heading'>
      <h2>만든 산출물</h2>
      {items.length > 0 && <span>{formatNumber(items.length)}건 · 최근에 만든 것이 위</span>}
    </div>

    {query.isPending
      ? <p className='deliverable-history-empty'>목록을 불러오는 중입니다.</p>
      : query.isError
        ? <p className='deliverable-history-empty'>목록을 불러오지 못했습니다. {query.error?.message}</p>
        : items.length === 0
          ? <p className='deliverable-history-empty'>아직 만든 산출물이 없습니다. 위에서 조건과 형식을 고른 뒤 <strong>만들기</strong>를 누르면 여기에 쌓입니다.</p>
          : <ul className='deliverable-history-list'>
            {items.map(item => <HistoryItem
              key={item.id}
              item={item}
              downloading={item.id === downloadingId}
              onDownload={onDownload}
              onDelete={onDelete}
            />)}
          </ul>}
  </section>
}

// 한 건. **낡았는지를 배지 하나로 끝내지 않고 무엇이 늘었는지 적는다** —
// "갱신 필요" 만 보이면 사용자는 다시 만들어도 무엇이 달라지는지 모른다.
//
// is_stale 을 화면에서 계산하지 않는다. 서버가 생성 시각 이후 재료를 세어 판정하고,
// 늘어난 것만 stale_changes 에 담아 준다(DLV-003-4).
function HistoryItem({ item, downloading, onDownload, onDelete }) {
  const changes = staleSentence(item.stale_changes)
  return <li className={'deliverable-card' + (item.is_stale ? ' is-stale' : '')}>
    <div className='deliverable-card-main'>
      <div className='deliverable-card-title'>
        <strong>{item.title}</strong>
        <span className='deliverable-card-format'>{item.format}</span>
        {item.is_stale && <span className='deliverable-card-badge'>갱신 필요</span>}
      </div>
      <p className='deliverable-card-meta'>
        {formatDateTime(item.generated_at)} · {formatFileSize(item.file_size)}
      </p>
      {item.is_stale && <p className='deliverable-card-stale'>
        {changes ? <>만든 뒤 {changes}이 늘었습니다. 다시 만들면 반영됩니다.</> : '만든 뒤 담길 내용이 바뀌었습니다. 다시 만들면 반영됩니다.'}
      </p>}
    </div>
    <div className='deliverable-card-actions'>
      <button type='button' disabled={downloading} onClick={() => onDownload(item)}>
        {downloading ? '받는 중…' : '내려받기'}
      </button>
      <button type='button' className='deliverable-card-delete' onClick={() => onDelete(item)}>삭제</button>
    </div>
  </li>
}

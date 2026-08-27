// =============================================================================
// 이 파일의 책임: 프로젝트 금액 현황 화면이다(AMT-003-2). 승인된 금액 항목의
//   합계와 원가구분별 내역을 보여주고, 합계에 들어가지 않은 것이 몇 건인지
//   함께 밝힌다.
// 다른 파일과의 관계: api/amount.js 의 getAmountSummary 를 부른다. 표기는
//   utils/format.js 의 formatMoney·formatNumber 를 쓴다. WorkspacePage 의
//   '금액' 탭에서 그린다. 단가 선례(AmountPrecedentPanel)는 검색 화면에 있다.
// Spring 비교: 서버가 만든 뷰 모델을 그대로 그리는 화면이다. 합계를 화면에서
//   다시 더하지 않는다.
//
// 계산을 화면에서 다시 하지 않는다
//   item_total + vat_total 을 더해 합계를 만들지 않는다. total_with_vat 가 이미
//   온다. 더하면 "부가세를 어떻게 합치는가" 라는 규칙이 서버와 화면 두 곳에
//   생기고, 규칙이 바뀔 때 한쪽만 틀린다. 그 종류의 오류는 에러가 나지 않고
//   숫자만 조용히 어긋난다.
//
//   같은 이유로 by_category 를 합쳐 검산하지 않는다. by_category 에는 VAT 행이
//   들어 있어서 합쳐도 item_total 이 되지 않는다 — 서버가 일부러 그렇게 준다
//   (원가구분별로는 부가세도 보여야 한다).
//
// "합계에 안 들어간 것" 을 반드시 함께 보여주는 이유
//   완료 판정이 "현황 수치가 정확히 집계돼 표시된다"(AMT-003-2) 인데, 빠진 것을
//   숨기면 숫자는 맞아도 사실이 아니다. 금액이 안 적힌 항목을 0 으로 더하면
//   합계는 그럴듯해지고 "금액을 모른다" 는 사실이 사라진다. 서버가 그것을
//   excluded_no_amount 로 따로 세는 것이 그 이유다.
//
// 승인 대기 항목이 왜 안 보이나
//   집계에 들어가는 상태를 서버가 included_decisions 로 알려준다(APPROVED·EDITED).
//   승인 전에는 어디에도 반영하지 않는 것이 AMT-001-2 의 완료 판정이다. 화면이
//   상태 목록을 외우지 않고 받은 값을 그대로 적는다.
// =============================================================================

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  approveAmountItem,
  cancelAmountItem,
  createTaskFromMismatch,
  getAmountItems,
  getAmountSummary,
  getPendingAmountItems,
  rejectAmountItem,
  updateAmountItem,
} from '../../api/amount'
import PageHeading from '../../components/common/PageHeading'
import { formatMoney, formatNumber } from '../../utils/format'
import './AmountSummaryView.css'

// 원가구분 표시 문구. 값은 서버의 _CATEGORY(models/amount.py)와 같아야 한다 —
// 리비전 0015 의 ck_amount_category CHECK 가 근거다.
//
// 여기 없는 값이 오면 코드를 그대로 보여준다. 임의로 '기타' 로 묶지 않는다 —
// 새 구분이 추가됐을 때 화면이 조용히 뭉개면 알아챌 방법이 없다.
const CATEGORY_LABELS = {
  DIRECT_LABOR: '직접인건비',
  EXPENSE: '직접경비',
  OVERHEAD: '제경비',
  TECH_FEE: '기술료',
  MATERIAL: '재료비·물품비',
  SUBCONTRACT: '외주비',
  VAT: '부가가치세',
  OTHER: '기타',
}

// 승인 상태 표시 문구. included_decisions 를 사람 말로 바꿀 때만 쓴다.
const DECISION_LABELS = { APPROVED: '승인', EDITED: '수정 승인' }

export default function AmountSummaryView({ projectId, notify }) {
  const summaryQuery = useQuery({
    queryKey: ['projects', projectId, 'amount-summary'],
    queryFn: () => getAmountSummary(projectId),
    retry: false,
  })
  const summary = summaryQuery.data

  // 항목 목록은 **펼칠 때** 부른다. 항목이 수백 줄인 프로젝트에서 합계만 보려고
  // 들어왔는데 매번 목록까지 받으면 느려진다.
  const [expanded, setExpanded] = useState(false)

  return <>
    <PageHeading
      eyebrow='AMOUNTS'
      title='금액'
      description='승인된 금액 항목만 집계합니다. 합계에 들어가지 않은 항목은 따로 셉니다.'
    />

    {/* 승인 대기 항목 (AMT-001-2). 있을 때만 맨 위에 띄운다 — 사용자가 금액
        페이지에 온 이유가 "대시보드의 승인 대기 N건" 을 처리하려는 것일 때가
        많아서, 합계보다 먼저 눈에 들어와야 한다. 0 건이면 스스로 사라진다. */}
    <PendingPanel projectId={projectId} notify={notify}/>

    {summaryQuery.isError && <section className='panel amount-notice'>
      <div>
        <strong>금액 현황을 불러오지 못했습니다.</strong>
        <p>{summaryQuery.error?.message}</p>
      </div>
      <button type='button' onClick={() => summaryQuery.refetch()}>다시 시도</button>
    </section>}

    <section className='amount-total-grid' aria-label='금액 합계'>
      <TotalCard
        label='항목 합계'
        note='부가가치세를 제외한 금액입니다.'
        value={summary?.item_total}
        currency={summary?.currency}
        loading={summaryQuery.isPending}
      />
      <TotalCard
        label='부가가치세'
        note='원가구분이 VAT 인 항목의 합입니다.'
        value={summary?.vat_total}
        currency={summary?.currency}
        loading={summaryQuery.isPending}
      />
      <TotalCard
        label='합계'
        note='부가가치세를 포함한 금액입니다.'
        value={summary?.total_with_vat}
        currency={summary?.currency}
        loading={summaryQuery.isPending}
        emphasis
      />
    </section>

    <section className='panel amount-scope' aria-label='집계 범위'>
      <h2>무엇을 집계했나</h2>
      {summaryQuery.isPending
        ? <p className='amount-scope-empty'>집계 범위를 확인하는 중입니다.</p>
        : <>
          <dl className='amount-scope-list'>
            <div>
              <dt>담긴 항목</dt>
              <dd>{formatNumber(summary?.included_item_count ?? 0)}건</dd>
            </div>
            <div>
              <dt>문서</dt>
              <dd>{formatNumber(summary?.document_count ?? 0)}건</dd>
            </div>
            <div>
              <dt>금액이 없어 빠진 항목</dt>
              <dd>{formatNumber(summary?.excluded_no_amount ?? 0)}건</dd>
            </div>
            <div>
              <dt>검산할 수 없는 항목</dt>
              <dd>{formatNumber(summary?.unverifiable_line_count ?? 0)}건</dd>
            </div>
          </dl>
          <p className='amount-scope-note'>
            {/* 어느 상태를 담았는지 서버가 알려준 값으로 적는다. 화면이 외우지 않는다. */}
            <strong>{describeDecisions(summary?.included_decisions)}</strong> 상태인 항목만 담았습니다.
            승인 대기 항목은 승인하면 합계에 들어갑니다.
          </p>
          {(summary?.excluded_no_amount ?? 0) > 0 && <p className='amount-scope-note'>
            금액이 적혀 있지 않은 항목은 <strong>0 원으로 더하지 않고 빼 두었습니다.</strong>
            0 으로 더하면 합계는 맞아 보이지만 금액을 모른다는 사실이 사라집니다.
          </p>}
          {(summary?.unverifiable_line_count ?? 0) > 0 && <p className='amount-scope-note'>
            수량이나 단가가 없어 <strong>수량 × 단가 검산을 못 한 항목</strong>이 있습니다.
            제경비·기술료처럼 비율로 산정된 항목이라 오류가 아닙니다.
          </p>}

          {/* 숫자만 보면 그것이 맞는지 확인할 방법이 없다. 무엇을 더했는지
              펼쳐서 볼 수 있게 한다(AMT-003-3). */}
          <button
            type='button'
            className='amount-toggle'
            aria-expanded={expanded}
            onClick={() => setExpanded(current => !current)}
          >{expanded ? '항목 숨기기' : `항목 보기 (${formatNumber(summary?.included_item_count ?? 0)}건)`}</button>

          {expanded && <ItemTable projectId={projectId} notify={notify}/>}
        </>}
    </section>

    <TotalCheckPanel summary={summary} loading={summaryQuery.isPending}/>

    <section className='panel amount-category' aria-label='원가구분별 금액'>
      <div className='amount-category-heading'>
        <h2>원가구분별</h2>
        <span>부가가치세도 한 줄로 함께 보여줍니다.</span>
      </div>
      {summaryQuery.isPending
        ? <p className='amount-scope-empty'>불러오는 중입니다.</p>
        : (summary?.by_category?.length ?? 0) === 0
          ? <p className='amount-scope-empty'>승인된 금액 항목이 아직 없습니다. 문서에서 금액을 추출하고 승인하면 여기에 쌓입니다.</p>
          : <table className='amount-category-table'>
            <thead>
              <tr>
                <th scope='col'>원가구분</th>
                <th scope='col' className='amount-cell-number'>금액</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_category.map(row => <tr key={row.category}>
                <th scope='row'>{CATEGORY_LABELS[row.category] ?? row.category}</th>
                <td className='amount-cell-number'>{formatMoney(row.amount)}</td>
              </tr>)}
            </tbody>
          </table>}
    </section>
  </>
}

/** included_decisions 를 '승인 · 수정 승인' 처럼 바꾼다. 값이 없으면 빈 문자열. */
function describeDecisions(decisions) {
  return (decisions ?? []).map(value => DECISION_LABELS[value] ?? value).join(' · ')
}

// 문서에 적힌 합계와 우리가 더한 합계를 나란히 보여준다 (AMT-002-1).
//
// 이 화면에서 가장 강한 정보다. 요약이나 결정사항은 AI 가 맞게 뽑았는지 확인할
// 방법이 없지만, 금액은 문서에 적힌 값과 맞춰볼 수 있다.
//
// **맞은 문서도 보여준다.** 불일치만 띄우면 "대조했고 맞았다" 와 "대조를 안 했다"
// 가 화면에서 같아 보인다. 앞은 증명이고 뒤는 정보가 없는 상태다.
//
// 대조하지 못한 문서는 **건수와 이유만** 적는다. 표에 빈 줄로 넣으면 합계가 없는
// 정상 문서가 오류처럼 보인다.
function TotalCheckPanel({ summary, loading }) {
  const checks = summary?.total_checks ?? []
  const missing = summary?.documents_without_stated_total ?? 0
  // **실제로 대조한 문서가 하나도 없으면 이 절을 통째로 숨긴다.** 문서에 「적힌
  // 합계」(documents.stated_total_amount)가 없으면 대조할 게 없어 "대조 못 함" 만
  // 뜨는데, 그건 정보가 아니라 잡음이다 — 자동 추출(AMT-001-1) 전에는 그 값이
  // 대부분 비어 있다. 대조할 게 하나라도 있을 때만 띄운다(로딩 중엔 checks 가
  // 비어 있어 자연히 숨겨지고, 값이 온 뒤 대조분이 있으면 나타난다).
  if (checks.length === 0) return null

  return <section className='panel amount-total-check' aria-label='문서 합계 대조'>
    <div className='amount-category-heading'>
      <h2>문서 합계 대조</h2>
      <span>문서에 적힌 합계와 항목을 더한 값을 맞춰봅니다.</span>
    </div>

    {loading
      ? <p className='amount-scope-empty'>대조하는 중입니다.</p>
      : <>
        {checks.length > 0 && <div className='amount-table-scroll'>
          <table className='amount-items-table'>
            <thead>
              <tr>
                <th scope='col'>문서</th>
                <th scope='col' className='amount-cell-number'>문서에 적힌 합계</th>
                <th scope='col' className='amount-cell-number'>항목을 더한 합계</th>
                <th scope='col'>대조</th>
              </tr>
            </thead>
            <tbody>
              {checks.map(row => <tr key={row.document_id} className={row.matches ? undefined : 'is-mismatch'}>
                <th scope='row'>
                  <span className='amount-item-source' title={row.filename}>{row.filename}</span>
                </th>
                <td className='amount-cell-number'>{formatMoney(row.stated_total)}</td>
                <td className='amount-cell-number'>{formatMoney(row.item_total)}</td>
                <td className={'amount-verify is-' + (row.matches ? 'ok' : 'bad')}>
                  {row.matches ? '일치' : totalGapText(row.difference)}
                </td>
              </tr>)}
            </tbody>
          </table>
        </div>}

        {/* 부가세를 빼고 비교한다는 사실을 반드시 적는다. 문서의 합계가 부가세를
            포함한 값이면 이 대조는 늘 불일치로 나오는데, 그 이유를 모르면
            계산이 틀렸다고 읽는다. */}
        {checks.length > 0 && <p className='amount-scope-note'>
          「항목을 더한 합계」는 <strong>부가가치세를 제외한 값</strong>입니다.
          문서의 합계가 부가세를 포함한 값이면 그만큼 차이가 납니다.
        </p>}

        {missing > 0 && <p className='amount-scope-note'>
          문서 <strong>{formatNumber(missing)}건</strong>은 적힌 합계가 없어 대조하지 못했습니다.
          공고문처럼 합계가 없는 문서가 있어서 <strong>오류가 아닙니다.</strong>
        </p>}
      </>}
  </section>
}

/** 문서 합계 차이를 문장으로. difference = 항목 합계 − 문서 합계 다.
 *  양수면 문서에 적힌 합계가 더 작다. 부호를 그대로 보여주지 않는 이유는
 *  항목 검산(verifyText)과 같다. */
function totalGapText(difference) {
  const gap = difference ?? 0
  return gap > 0
    ? `문서 합계가 ${formatMoney(gap)}원 적음`
    : `문서 합계가 ${formatMoney(Math.abs(gap))}원 많음`
}

// 목록 걸러보기. 서버가 준 값만 보고 나누므로 규칙을 화면이 다시 만들지 않는다.
//
// '검산 불가' 와 '어긋남' 을 **따로 두는 이유**: 제경비·기술료는 수량·단가가
// 원래 없어서 검산을 못 하는 것이고 오류가 아니다. 한 칸에 묶으면 정상 항목이
// 문제로 보인다. 서버의 verified 가 true·false·null 셋인 것과 같은 이유다.
const FILTERS = [
  ['all', '전체', () => true],
  ['mismatch', '어긋난 항목', row => row.verified === false],
  ['unverifiable', '검산 불가', row => row.verified === null && row.amount !== null],
  ['no-amount', '금액 없음', row => row.amount === null],
]

// 금액 항목 표(AMT-003-3). 「무엇을 집계했나」를 펼쳤을 때만 그린다.
function ItemTable({ projectId, notify }) {
  const [filter, setFilter] = useState('all')
  const queryClient = useQueryClient()
  const itemsQuery = useQuery({
    queryKey: ['projects', projectId, 'amount-items'],
    queryFn: () => getAmountItems(projectId),
    retry: false,
  })

  // 어긋난 항목을 태스크로 만든다 (AMT-004-3). **자동으로 만들지 않는다** —
  // 사람이 누를 때만 부른다. 그것이 완료 판정의 "자동 등록은 하지 않는다" 다.
  // 고치는 중인 항목. null 이면 편집 영역이 닫혀 있다.
  const [editing, setEditing] = useState(null)

  const taskMutation = useMutation({
    mutationFn: item => createTaskFromMismatch(projectId, item.id),
    onSuccess: task => notify?.('success', '태스크를 만들었습니다', task.title),
    onError: error => notify?.('error', '태스크를 만들지 못했습니다', error?.message),
    // **성공이든 실패든 목록을 다시 받는다.** 실패 사유 셋(항목이 없다 · 어긋난
    // 항목이 아니다 · 이미 태스크가 있다)이 모두 "화면이 낡았다" 는 뜻이라,
    // 다시 받는 것이 사용자가 해야 할 일이다.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'amount-items'] })
      // 보드가 열려 있으면 새 태스크가 보여야 한다.
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'tasks'] })
    },
  })

  // 승인 취소 (APPROVED/EDITED → PENDING). 잘못 승인한 항목을 무른다 — 집계에서
  // 빠지고 「승인 대기」에 다시 나타난다. 그래서 대기 목록·대시보드 건수도 갱신한다.
  const cancelMutation = useMutation({
    mutationFn: item => cancelAmountItem(projectId, item.id),
    onSuccess: (_row, item) => notify?.('success', '승인을 취소했습니다', `${item.item_name} — 승인 대기로 되돌렸습니다.`),
    onError: error => notify?.('error', '취소하지 못했습니다', error?.message),
    onSettled: () => {
      for (const key of ['amount-items', 'amount-summary', 'amount-pending', 'dashboard']) {
        queryClient.invalidateQueries({ queryKey: ['projects', projectId, key] })
      }
    },
  })

  const rows = itemsQuery.data?.items ?? []
  const matcher = FILTERS.find(([key]) => key === filter)?.[2] ?? (() => true)
  const visible = rows.filter(matcher)

  if (itemsQuery.isPending) return <p className='amount-scope-empty'>항목을 불러오는 중입니다.</p>
  if (itemsQuery.isError) return <p className='amount-scope-empty'>항목을 불러오지 못했습니다. {itemsQuery.error?.message}</p>
  if (rows.length === 0) return <p className='amount-scope-empty'>승인된 금액 항목이 없습니다.</p>

  return <div className='amount-items'>
    <div className='amount-filters' role='group' aria-label='항목 걸러보기'>
      {FILTERS.map(([key, label, match]) => {
        // 건수는 **받아온 목록에서** 센다. 상한에 걸려 잘렸으면 전체가 아니므로
        // 아래에 잘렸다는 사실을 함께 적는다.
        const count = rows.filter(match).length
        return <button
          className={'amount-filter' + (key === filter ? ' is-active' : '')}
          type='button'
          key={key}
          aria-pressed={key === filter}
          disabled={count === 0 && key !== 'all'}
          onClick={() => setFilter(key)}
        >{label} {formatNumber(count)}</button>
      })}
    </div>

    {itemsQuery.data?.truncated && <p className='amount-scope-note'>
      전체 <strong>{formatNumber(itemsQuery.data.total)}건</strong> 중 앞
      {formatNumber(itemsQuery.data.returned)}건만 보여줍니다. 위 건수도 보여준 것만 센 값입니다.
    </p>}

    <div className='amount-table-scroll'>
      <table className='amount-items-table'>
        <thead>
          <tr>
            <th scope='col'>항목</th>
            <th scope='col'>원가구분</th>
            <th scope='col' className='amount-cell-number'>수량 × 단가</th>
            <th scope='col' className='amount-cell-number'>문서 금액</th>
            <th scope='col'>검산</th>
            <th scope='col'>원문 근거</th>
            <th scope='col'>태스크</th>
            <th scope='col'>관리</th>
          </tr>
        </thead>
        <tbody>
          {visible.map(row => <ItemRow
            key={row.id}
            row={row}
            pending={taskMutation.isPending && taskMutation.variables?.id === row.id}
            editing={editing?.id === row.id}
            cancelPending={cancelMutation.isPending && cancelMutation.variables?.id === row.id}
            onCreateTask={item => taskMutation.mutate(item)}
            onEdit={item => setEditing(item)}
            onCancel={item => cancelMutation.mutate(item)}
          />)}
        </tbody>
      </table>
    </div>

    {visible.length === 0 && <p className='amount-scope-empty'>이 조건에 맞는 항목이 없습니다.</p>}

    {editing && <ItemEditor
      key={editing.id}
      projectId={projectId}
      item={editing}
      notify={notify}
      onClose={() => setEditing(null)}
    />}
  </div>
}

// 원가구분 선택 목록. CATEGORY_LABELS 에서 만든다 — 두 곳에 적으면 한쪽만 고쳐서
// 표와 선택 목록이 다른 이름을 쓰게 된다.
const CATEGORY_OPTIONS = Object.entries(CATEGORY_LABELS)

/** 값을 입력칸에 넣을 문자열로. null·undefined 는 빈 칸이다. */
function toInput(value) {
  return value === null || value === undefined ? '' : String(value)
}

// 금액 항목 고치기 (AMT-001-2). 표 아래에 펼친다.
//
// **보낸 필드만 서버에 넘긴다.** 처음 값과 비교해 바뀐 것만 담는다 — 안 바꾼 필드를
// 함께 보내면 그 값을 «다시 확정» 하는 셈이고, 두 사람이 같은 항목의 다른 칸을
// 고칠 때 나중 사람이 앞사람의 변경을 덮어쓴다.
//
// 빈 칸은 null 로 보낸다. 「비웠다」와 「안 건드렸다」가 다르므로, 처음에 값이
// 있었는데 비운 경우만 null 이 된다.
function ItemEditor({ projectId, item, notify, onClose }) {
  const [form, setForm] = useState({
    quantity: toInput(item.quantity),
    unit: toInput(item.unit),
    unit_price: toInput(item.unit_price),
    amount: toInput(item.amount),
    category: item.category ?? '',
  })
  const queryClient = useQueryClient()

  const saveMutation = useMutation({
    mutationFn: changes => updateAmountItem(projectId, item.id, changes),
    onSuccess: row => {
      // 서버가 다시 검산해서 돌려준다. 화면이 곱해서 판단하지 않는다.
      //
      // 태스크가 연결돼 있으면 보드를 가리킨다. 시스템이 태스크를 지우거나 완료로
      // 옮기지 않으므로(completed_at 이 주간 보고서의 재료다) 사람이 처리해야 한다.
      // 그 사실을 알리지 않으면 보드에 이유 모를 태스크가 남는다.
      const detail = row.verified === true ? '검산이 맞았습니다.' : verifyText(row)[0]
      notify?.(
        'success',
        '금액 항목을 수정했습니다',
        row.task_id
          ? `${detail} 연결된 태스크에도 적었습니다 — 보드에서 확인해 주세요.`
          : detail,
      )
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'amount-items'] })
      // 합계·원가구분별·문서 합계 대조가 다 바뀐다.
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'amount-summary'] })
      // 대기 항목을 수정하면 EDITED(=승인)가 되어 승인 대기 목록·대시보드 건수에서 빠진다.
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'amount-pending'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'dashboard'] })
      onClose()
    },
    onError: error => notify?.('error', '고치지 못했습니다', error?.message),
  })

  const set = (field, value) => setForm(current => ({ ...current, [field]: value }))

  const submit = event => {
    event.preventDefault()
    const changes = {}
    for (const [field, initial] of [
      ['quantity', toInput(item.quantity)],
      ['unit', toInput(item.unit)],
      ['unit_price', toInput(item.unit_price)],
      ['amount', toInput(item.amount)],
      ['category', item.category ?? ''],
    ]) {
      const next = form[field]
      if (next === initial) continue
      // 빈 칸은 «비웠다» 다. 서버가 null 을 받아 컬럼을 비운다.
      changes[field] = next === '' ? null : next
    }
    if (Object.keys(changes).length === 0) {
      notify?.('info', '바뀐 값이 없습니다', '고칠 값을 하나 이상 바꿔 주세요.')
      return
    }
    saveMutation.mutate(changes)
  }

  return <form className='amount-edit' onSubmit={submit}>
    <div className='amount-edit-heading'>
      <strong>{item.item_name} 수정</strong>
      <span>{item.filename}</span>
    </div>

    <div className='amount-edit-fields'>
      <label>
        <span>수량</span>
        <input type='number' step='any' min='0' value={form.quantity} onChange={e => set('quantity', e.target.value)}/>
      </label>
      <label>
        <span>단위</span>
        <input value={form.unit} maxLength={30} onChange={e => set('unit', e.target.value)}/>
      </label>
      <label>
        <span>단가</span>
        <input type='number' step='1' min='0' value={form.unit_price} onChange={e => set('unit_price', e.target.value)}/>
      </label>
      {/* 문서에 적힌 금액. 고치면 문서의 오류가 감춰지므로 구분해 둔다. */}
      <label className='is-caution'>
        <span>문서에 적힌 금액</span>
        <input type='number' step='1' min='0' value={form.amount} onChange={e => set('amount', e.target.value)}/>
      </label>
      <label>
        <span>원가구분</span>
        <select value={form.category} onChange={e => set('category', e.target.value)}>
          <option value=''>판별 안 됨</option>
          {CATEGORY_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select>
      </label>
    </div>

    <p className='amount-edit-note'>
      우리가 문서를 잘못 읽었다면 <strong>수량·단위·단가</strong>를 고치세요.
      「문서에 적힌 금액」을 고치는 것은 <strong>마지막 선택</strong>입니다 —
      그 값을 바꾸면 문서 자체의 오류가 감춰져서 합계 대조가 무의미해집니다.
    </p>
    <p className='amount-edit-note'>
      저장하면 <strong>사람이 확인한 값(EDITED)</strong>으로 남고 합계·검산에 바로 반영됩니다.
    </p>
    {/* 「비우기」와 「0」은 다르다. 이걸 안 적으면 수량을 없애려고 0 을 넣고
        계산값이 0원이 되는 것을 고장으로 읽는다 — 실제로 겪은 일이다. */}
    <p className='amount-edit-note'>
      <strong>빈 칸으로 두면 그 값을 비웁니다</strong> — 검산을 하지 않습니다(제경비처럼 수량·단가가
      원래 없는 항목에 씁니다). <strong>0 을 넣으면 «0 이라고 적혀 있다»</strong> 는 뜻이라
      계산값이 0원이 됩니다. 둘은 다릅니다.
    </p>

    <div className='amount-edit-actions'>
      <button type='submit' className='is-primary' disabled={saveMutation.isPending}>
        {saveMutation.isPending ? '저장 중…' : '저장'}
      </button>
      <button type='button' onClick={onClose} disabled={saveMutation.isPending}>닫기</button>
    </div>
  </form>
}

// 원문 근거를 표에서 한 줄로 줄이는 기준 글자 수.
//
// **이 길이를 넘을 때만 마우스 올림 안내(title·물음표 커서)를 붙인다.** 짧은 근거는
// 이미 다 보이는데 툴팁을 띄우면 같은 말을 두 번 하고, 물음표 커서가 "더 있다" 고
// 약속해놓고 없는 상태가 된다.
//
// 픽셀이 아니라 글자 수로 재는 것은 어림이다. 정확히 하려면 그린 뒤에
// scrollWidth 와 clientWidth 를 비교해야 하는데, 줄마다 ref 를 달고 다시 그려야
// 해서 얻는 것보다 복잡하다. 어긋나도 손해가 "툴팁이 한 번 더 뜬다" 뿐이다.
const QUOTE_INLINE_MAX = 24

function ItemRow({ row, pending, editing, cancelPending, onCreateTask, onEdit, onCancel }) {
  const [text, tone] = verifyText(row)
  const quote = row.source_quote || ''
  const quoteClipped = quote.length > QUOTE_INLINE_MAX
  return <tr className={tone === 'bad' ? 'is-mismatch' : undefined}>
    <th scope='row'>
      <strong>{row.item_name}</strong>
      {/* 어느 문서에서 나온 값인지. 근거를 되짚는 출발점이다. */}
      <span className='amount-item-source' title={row.filename}>{row.filename}</span>
      {/* 이 목록은 승인된 것만 담는다(서버가 APPROVED·EDITED 만 준다). 어떤 방식으로
          승인됐는지 배지로 밝혀, 승인 대기와 헷갈리지 않게 한다. */}
      {row.decision && <span className='amount-decision'>{DECISION_LABELS[row.decision] ?? row.decision}</span>}
    </th>
    <td>{row.category ? CATEGORY_LABELS[row.category] ?? row.category : '—'}</td>
    <td className='amount-cell-number'>{quantityText(row)}</td>
    <td className='amount-cell-number'>{row.amount === null ? '—' : formatMoney(row.amount)}</td>
    <td className={'amount-verify is-' + tone}>{text}</td>
    <td
      className={'amount-quote' + (quoteClipped ? ' is-clipped' : '')}
      title={quoteClipped ? quote : undefined}
    >{quote || '—'}</td>
    {/* 어긋난 항목만 태스크로 만들 수 있다. 서버도 같은 판정을 다시 하므로
        여기서 막는 것은 «누를 수 없게 보이는 것» 까지다. */}
    <td className='amount-task-cell'>
      {row.task_id
        ? <span className='amount-task-done'>태스크 있음</span>
        : tone === 'bad'
          ? <button type='button' className='amount-task-button' disabled={pending} onClick={() => onCreateTask(row)}>
            {pending ? '만드는 중…' : '태스크로 만들기'}
          </button>
          : <span className='amount-task-none'>—</span>}
    </td>
    {/* 관리: 수정(값 정정, →EDITED) · 취소(승인 무름, →PENDING). 모든 항목을 고칠
        수 있다 — 맞은 항목도 원가구분이 틀렸거나 단위가 잘못 읽혔을 수 있다.
        취소는 잘못 승인된 것을 「승인 대기」로 되돌린다(거절과 달리 되살릴 수 있다). */}
    <td className='amount-task-cell amount-manage-cell'>
      <button type='button' className='amount-task-button' disabled={editing || cancelPending} onClick={() => onEdit(row)}>
        {editing ? '수정 중' : '수정'}
      </button>
      <button type='button' className='amount-task-button is-cancel' disabled={editing || cancelPending} onClick={() => onCancel(row)}>
        {cancelPending ? '취소 중…' : '취소'}
      </button>
    </td>
  </tr>
}

/** '3 인월 × 8,500,000' 또는 검산할 수 없으면 '—'. 곱셈은 서버가 한 값을 쓴다. */
function quantityText(row) {
  if (row.quantity === null || row.quantity === undefined || row.unit_price === null) return '—'
  return `${formatMoney(row.quantity)}${row.unit ? ' ' + row.unit : ''} × ${formatMoney(row.unit_price)}`
}

/** 검산 결과를 사람 문장으로. **부호를 그대로 보여주지 않는다.**
 *
 *  difference = expected - amount 라서, 문서 금액이 더 크면 음수다. `-50,000`
 *  만 띄우면 "5만원 부족" 으로 읽힌다. 어느 쪽이 큰지 말로 적는다.
 *
 *  verified 가 셋(true·false·null)이므로 분기도 셋이다. null 을 false 와 묶으면
 *  제경비처럼 비율로 산정된 항목이 틀린 항목으로 보인다.
 */
function verifyText(row) {
  if (row.excluded_reason) return ['금액 없음', 'muted']
  if (row.verified === true) return ['맞음', 'ok']
  if (row.verified === null) return ['검산 불가', 'muted']
  // 계산값이 0원인 경우를 따로 말한다.
  //
  // 수량이나 단가가 0 이면 수량 × 단가가 0원이 되는데, 그때 "문서 금액이
  // 200,000원 많음" 이라고만 적으면 **계산값이 0 이라는 사실이 감춰진다.**
  // 사용자는 금액이 조금 어긋난 줄로 읽는다.
  //
  // 0 을 «검산 불가» 로 바꾸지 않는 이유: 비어 있는 것(NULL)과 0 은 다르다.
  // NULL 은 "문서에 안 적혀 있다"(제경비), 0 은 "문서에 0 이라고 적혀 있다" 다.
  // 그리고 수량 0 에 금액 200,000 인 줄은 실제로 앞뒤가 안 맞으므로 잡아야 한다.
  if (row.expected === 0) return ['수량 × 단가가 0원입니다', 'bad']
  const gap = row.difference ?? 0
  return [
    gap > 0
      ? `문서 금액이 ${formatMoney(gap)}원 적음`
      : `문서 금액이 ${formatMoney(Math.abs(gap))}원 많음`,
    'bad',
  ]
}

// 합계 카드 하나. 통화를 값 옆에 적는다 — 서버가 currency 를 주는데 화면이
// '원' 을 하드코딩하면 다른 통화가 들어올 때 거짓말이 된다.
function TotalCard({ label, note, value, currency, loading, emphasis }) {
  return <div className={'panel amount-total-card' + (emphasis ? ' is-emphasis' : '')}>
    <span>{label}</span>
    <strong>
      {loading ? '—' : formatMoney(value)}
      {!loading && value !== null && value !== undefined && <em>{currency ?? ''}</em>}
    </strong>
    <p>{note}</p>
  </div>
}



// 승인 대기 금액 항목 (AMT-001-2). 문서에서 뽑았지만 아직 승인·거절되지 않은
// 것들이다. **승인해야 합계·선례·산출물에 들어간다** — 승인 전에는 어디에도
// 반영하지 않는 것이 완료 판정이다. 0 건이면 아무것도 그리지 않는다(스스로 사라짐).
//
// 승인 목록(ItemTable)과 따로 두는 이유: 저쪽은 «이미 승인된 것의 현황·검산»
// 이고 여기는 «아직 결정 안 된 것의 처리» 다. 대상이 다르므로 서버도 목록을
// 나눠 준다(getPendingAmountItems vs getAmountItems). 한 표에 섞으면 "이건
// 반영된 값인가" 가 흐려진다.
function PendingPanel({ projectId, notify }) {
  const queryClient = useQueryClient()
  const pendingQuery = useQuery({
    queryKey: ['projects', projectId, 'amount-pending'],
    queryFn: () => getPendingAmountItems(projectId),
    retry: false,
  })
  // 승인·거절 뒤에는 대기 목록·합계·항목목록·대시보드 승인대기 건수가 모두
  // 바뀐다. 한곳에서 무효화해 화면들이 어긋나지 않게 한다.
  const invalidateAll = () => {
    for (const key of ['amount-pending', 'amount-summary', 'amount-items', 'dashboard']) {
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, key] })
    }
  }

  const approveMutation = useMutation({
    mutationFn: item => approveAmountItem(projectId, item.id),
    onSuccess: (_row, item) => notify?.('success', '승인했습니다', `${item.item_name} — 합계에 반영됩니다.`),
    onError: error => notify?.('error', '승인하지 못했습니다', error?.message),
    onSettled: invalidateAll,
  })
  const rejectMutation = useMutation({
    mutationFn: item => rejectAmountItem(projectId, item.id),
    onSuccess: (_row, item) => notify?.('success', '거절했습니다', `${item.item_name} — 집계에서 빠집니다.`),
    onError: error => notify?.('error', '거절하지 못했습니다', error?.message),
    onSettled: invalidateAll,
  })

  // 대기 조회 실패·로딩은 화면 전체를 막지 않는다 — 합계는 따로 뜬다. 조용히 접는다.
  if (pendingQuery.isPending || pendingQuery.isError) return null
  const rows = pendingQuery.data?.items ?? []
  if (rows.length === 0) return null

  // 처리 중인 항목 id (버튼 비활성화용). 승인·거절 둘 중 도는 것을 본다.
  const busyId = approveMutation.isPending
    ? approveMutation.variables?.id
    : rejectMutation.isPending
      ? rejectMutation.variables?.id
      : null

  return <section className='panel amount-pending' aria-label='승인 대기 금액'>
    <div className='amount-category-heading'>
      <h2>승인 대기 <span className='amount-pending-count'>{formatNumber(pendingQuery.data.total)}건</span></h2>
      <span>문서에서 뽑은 금액입니다. 승인해야 합계·선례·산출물에 들어갑니다.</span>
    </div>

    {pendingQuery.data.truncated && <p className='amount-scope-note'>
      전체 <strong>{formatNumber(pendingQuery.data.total)}건</strong> 중 앞
      {formatNumber(pendingQuery.data.returned)}건만 보여줍니다.
    </p>}

    <div className='amount-table-scroll'>
      <table className='amount-items-table'>
        <thead>
          <tr>
            <th scope='col'>항목</th>
            <th scope='col'>원가구분</th>
            <th scope='col' className='amount-cell-number'>수량 × 단가</th>
            <th scope='col' className='amount-cell-number'>문서 금액</th>
            <th scope='col'>검산</th>
            <th scope='col'>원문 근거</th>
            <th scope='col'>처리</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => <PendingRow
            key={row.id}
            row={row}
            busy={busyId === row.id}
            onApprove={item => approveMutation.mutate(item)}
            onReject={item => rejectMutation.mutate(item)}
          />)}
        </tbody>
      </table>
    </div>
  </section>
}

// 승인 대기 한 줄. 검산 표시는 승인 목록과 같은 helper(verifyText·quantityText)를
// 써서 두 화면이 같은 규칙으로 읽히게 한다. 처리 버튼은 승인·거절 둘뿐이다 —
// 값 정정(수정)은 승인한 뒤 아래 집계 목록에서 한다.
function PendingRow({ row, busy, onApprove, onReject }) {
  const [text, tone] = verifyText(row)
  const quote = row.source_quote || ''
  const quoteClipped = quote.length > QUOTE_INLINE_MAX
  const locked = busy
  return <tr className={tone === 'bad' ? 'is-mismatch' : undefined}>
    <th scope='row'>
      <strong>{row.item_name}</strong>
      <span className='amount-item-source' title={row.filename}>{row.filename}</span>
    </th>
    <td>{row.category ? CATEGORY_LABELS[row.category] ?? row.category : '—'}</td>
    <td className='amount-cell-number'>{quantityText(row)}</td>
    <td className='amount-cell-number'>{row.amount === null ? '—' : formatMoney(row.amount)}</td>
    <td className={'amount-verify is-' + tone}>{text}</td>
    <td
      className={'amount-quote' + (quoteClipped ? ' is-clipped' : '')}
      title={quoteClipped ? quote : undefined}
    >{quote || '—'}</td>
    {/* 여기선 받아들일지(승인)·뺄지(거절)만 정한다. 값 정정은 승인한 뒤 아래
        「무엇을 집계했나 → 항목 보기」에서 «수정» 으로 한다 — 대기와 집계의
        역할을 갈라 둔다. 승인만 강조색으로 채워 기본 동작임을 보인다. */}
    <td className='amount-pending-actions'>
      <button type='button' className='amount-task-button is-approve' disabled={locked} onClick={() => onApprove(row)}>
        {busy ? '처리 중…' : '승인'}
      </button>
      <button type='button' className='amount-task-button is-reject' disabled={locked} onClick={() => onReject(row)}>거절</button>
    </td>
  </tr>
}

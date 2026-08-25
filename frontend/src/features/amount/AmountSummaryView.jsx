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
import { useQuery } from '@tanstack/react-query'
import { getAmountItems, getAmountSummary } from '../../api/amount'
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

export default function AmountSummaryView({ projectId }) {
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

          {expanded && <ItemTable projectId={projectId}/>}
        </>}
    </section>

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
function ItemTable({ projectId }) {
  const [filter, setFilter] = useState('all')
  const itemsQuery = useQuery({
    queryKey: ['projects', projectId, 'amount-items'],
    queryFn: () => getAmountItems(projectId),
    retry: false,
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
          </tr>
        </thead>
        <tbody>
          {visible.map(row => <ItemRow key={row.id} row={row}/>)}
        </tbody>
      </table>
    </div>

    {visible.length === 0 && <p className='amount-scope-empty'>이 조건에 맞는 항목이 없습니다.</p>}
  </div>
}

function ItemRow({ row }) {
  const [text, tone] = verifyText(row)
  return <tr className={tone === 'bad' ? 'is-mismatch' : undefined}>
    <th scope='row'>
      <strong>{row.item_name}</strong>
      {/* 어느 문서에서 나온 값인지. 근거를 되짚는 출발점이다. */}
      <span className='amount-item-source' title={row.filename}>{row.filename}</span>
    </th>
    <td>{row.category ? CATEGORY_LABELS[row.category] ?? row.category : '—'}</td>
    <td className='amount-cell-number'>{quantityText(row)}</td>
    <td className='amount-cell-number'>{row.amount === null ? '—' : formatMoney(row.amount)}</td>
    <td className={'amount-verify is-' + tone}>{text}</td>
    {/* 원문 근거는 길다. 표에서는 한 줄로 줄이고 마우스를 올리면 title 로 전체가
        보인다. 전부 펼치면 표가 읽히지 않는다. */}
    <td className='amount-quote' title={row.source_quote ?? ''}>{row.source_quote || '—'}</td>
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

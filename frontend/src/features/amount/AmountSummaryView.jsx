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

import { useQuery } from '@tanstack/react-query'
import { getAmountSummary } from '../../api/amount'
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

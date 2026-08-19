// =============================================================================
// 이 파일의 책임: 과거 유사 사업의 단가 선례를 찾아 보여준다(SRH-002-3).
//   항목명을 받아 조회하고, 요약(최저·중앙값·최고)과 선례 목록을 그린다.
// 다른 파일과의 관계: api/amount.js 로 조회한다. 지금은
//   features/search/SearchView.jsx 가 쓴다.
// Spring 비교: 화면 조각(컴포넌트) 하나. 서버가 만든 응답을 그대로 그린다.
//
// features/search 가 아니라 features/amount 에 둔 이유
//   기능 ID 는 SRH-002-3(검색)이지만, 실제 사용 맥락은 **금액을 검토하다가**
//   "이 단가가 적정한가" 를 묻는 것이다. 금액 화면(AMT-003-2)이 생기면 거기서도
//   같은 패널을 부른다. search 안에 두면 그때 옮기거나 복사해야 한다.
//
// 계산을 하지 않는다
//   금액은 문자열(Decimal)로 온다. 중앙값·최저·최고는 **서버가 계산해서 준다**
//   (services/amount_precedent_service.median). 화면에서 숫자로 바꿔 다시 계산하면
//   조달 금액 크기에서 정밀도가 깨진다. 여기서는 형식만 입힌다.
// =============================================================================

import { useState } from 'react'
import { findAmountPrecedents } from '../../api/amount'
import { formatMoney } from '../../utils/format'
import './AmountPrecedentPanel.css'

// 원가구분 표기. models/enums.py 의 AmountCategory 8종이다.
// null 은 "판별하지 못했다" 이고 OTHER(기타)와 다르다 — 그래서 따로 표시한다.
const CATEGORY_LABELS = {
  DIRECT_LABOR: '직접인건비',
  EXPENSE: '경비',
  OVERHEAD: '제경비',
  TECH_FEE: '기술료',
  MATERIAL: '재료비',
  SUBCONTRACT: '외주비',
  VAT: '부가세',
  OTHER: '기타',
}

const DECISION_LABELS = { APPROVED: '승인됨', EDITED: '수정 후 승인' }

// 결과에 인월 항목이 있는지. 있을 때만 용어 설명을 띄운다.
//
// 단위를 목록으로 두지 않고 '인월' 하나만 본다. 식·건·개·㎡ 는 따로 설명할 것이
// 없고, 설명이 필요한 단위가 더 생기면 그때 표로 만든다 — 지금 표를 만들면
// 값이 하나뿐인 표가 된다.
function hasManMonth(data) {
  return (data?.precedents ?? []).some(item => item.unit === '인월')
}

export default function AmountPrecedentPanel({ projectId }) {
  const [draft, setDraft] = useState('')
  const [state, setState] = useState({ status: 'idle', data: null, error: null, asked: '' })

  async function submit(event) {
    event.preventDefault()
    const itemName = draft.trim()
    if (!itemName) return
    setState({ status: 'loading', data: null, error: null, asked: itemName })
    try {
      const data = await findAmountPrecedents(projectId, { itemName })
      setState({ status: 'done', data, error: null, asked: itemName })
    } catch (error) {
      setState({ status: 'error', data: null, error, asked: itemName })
    }
  }

  return <section className="precedent" aria-label="과거 단가 선례">
    <form className="precedent-form" onSubmit={submit}>
      <input
        className="precedent-input"
        value={draft}
        onChange={event => setDraft(event.target.value)}
        placeholder="항목명으로 찾습니다. 예: 특급기술자"
        maxLength={300}
        aria-label="찾을 항목명"
      />
      <button className="precedent-submit" type="submit" disabled={state.status === 'loading' || !draft.trim()}>
        {state.status === 'loading' ? '찾는 중...' : '선례 찾기'}
      </button>
    </form>

    {/* 범위를 화면에서 고르지 않는다는 사실을 밝힌다. 서버가 "내 멤버십 −
        현재 프로젝트" 로 정하므로, 사용자가 범위를 바꿀 수단이 없는 것이
        의도임을 알려야 "왜 이 프로젝트 것이 안 나오나" 를 묻지 않는다. */}
    <p className="precedent-hint">
      <b>지금 프로젝트를 뺀</b> 내가 참여한 다른 프로젝트에서 찾습니다.
      승인된 항목({DECISION_LABELS.APPROVED} · {DECISION_LABELS.EDITED})만 선례로 씁니다.
    </p>

    {state.status === 'error' && <div className="precedent-box precedent-box--error">
      <strong>선례를 불러오지 못했습니다.</strong>
      <p>{state.error?.message}</p>
      {state.error?.code && <p className="precedent-code">코드 {state.error.code}</p>}
    </div>}

    {/* 「인월」 설명을 여기 한 번만 둔다. 줄마다 붙이면 선례 20건에서 스무 번
        반복돼 오히려 안 읽힌다. 결과에 인월 항목이 있을 때만 보여 준다 —
        식·건·개 단위만 나온 결과에는 필요 없는 설명이다. */}
    {state.status === 'done' && hasManMonth(state.data) && <p className="precedent-hint precedent-hint--term">
      <b>인월</b>은 1명이 1개월 일하는 양입니다. <b>3인월</b>은 3명이 1개월일 수도, 1명이 3개월일 수도 있어
      사람 수는 알 수 없습니다.
    </p>}

    {state.status === 'done' && <Result data={state.data} asked={state.asked}/>}

    {state.status === 'idle' && <div className="precedent-box">
      <strong>항목명을 넣고 찾아 보세요.</strong>
      <p>과거 사업의 단가를 <b>출처 문서와 함께</b> 보여 줍니다. 지금 사업의 단가가 적정한지 판단하는 데 씁니다.</p>
    </div>}
  </section>
}

function Result({ data, asked }) {
  const { summary, precedents = [], searched_project_ids: searched = [] } = data ?? {}

  // 찾아본 프로젝트가 0곳인 경우와 선례가 0건인 경우는 원인이 다르다.
  // 앞은 "내가 참여한 다른 프로젝트가 없다", 뒤는 "있는데 그 항목이 없다".
  // 같은 문구를 쓰면 사용자가 무엇을 해야 할지 알 수 없다.
  if (!searched.length) return <div className="precedent-box">
    <strong>찾아볼 다른 프로젝트가 없습니다.</strong>
    <p>선례는 <b>지금 프로젝트를 뺀</b> 내가 참여한 프로젝트에서 찾습니다. 참여 중인 프로젝트가 이것뿐입니다.</p>
  </div>

  if (!precedents.length) return <div className="precedent-box">
    <strong>&ldquo;{asked}&rdquo; 의 단가 선례를 찾지 못했습니다.</strong>
    <p>프로젝트 {searched.length}곳을 찾아봤습니다. 항목명이 다르게 적혀 있을 수 있습니다 — 문서에 쓰인 표기를 그대로 넣어 보세요.</p>
    <p className="precedent-meta">단가가 없는 항목(제경비·기술료처럼 비율로 산정된 것)과 승인 전 항목은 선례에서 제외됩니다.</p>
  </div>

  return <>
    {summary && <div className="precedent-summary">
      <Stat label="선례" value={`${summary.count}건`}/>
      <Stat label="최저 단가" value={formatMoney(summary.min_unit_price)}/>
      <Stat label="중앙값" value={formatMoney(summary.median_unit_price)} emphasis/>
      <Stat label="최고 단가" value={formatMoney(summary.max_unit_price)}/>
    </div>}

    {/* 중앙값을 강조하는 이유를 화면에 적어 둔다. 평균이 아닌 것이 의도임을
        알려야 "왜 평균이 없나" 를 묻지 않는다. */}
    {summary && <p className="precedent-meta">
      선례가 적을 때 한 건의 이상치가 평균을 끌고 가므로 <b>평균이 아니라 중앙값</b>을 씁니다.
    </p>}

    <ul className="precedent-list">
      {precedents.map(item => <PrecedentRow item={item} key={`${item.document_id}-${item.item_name}-${item.unit_price}`}/>)}
    </ul>

    <p className="precedent-meta">찾아본 프로젝트 {searched.length}곳 · 선례 {precedents.length}건</p>
  </>
}

function Stat({ label, value, emphasis }) {
  return <div className={'precedent-stat' + (emphasis ? ' is-emphasis' : '')}>
    <span>{label}</span><strong>{value}</strong>
  </div>
}

function PrecedentRow({ item }) {
  const category = item.category ? (CATEGORY_LABELS[item.category] ?? item.category) : null
  return <li className="precedent-item">
    <div className="precedent-item__main">
      <strong>{item.item_name}</strong>
      {/* 문서 유형은 응답에 없다. 필요하면 schemas/amount_precedent.py 에
          document_type 을 더해야 한다 — 없는 필드를 참조해 두면 나중에 읽는
          사람이 있다고 착각한다. */}
      <p className="precedent-item__where">{item.project_name} · {item.document_filename}</p>
      {/* 출처 인용. 완료 판정이 "단가가 출처와 함께 표시된다" 이므로 이 줄이 핵심이다 */}
      {item.source_quote && <p className="precedent-item__quote">{item.source_quote}</p>}
    </div>
    <div className="precedent-item__figures">
      {/* 단가에 "무엇 하나의 값인지" 를 붙인다. 8,800,000 만 있으면 사업 전체
          금액으로 읽힐 수 있다.
          단위를 하드코딩하지 않는다 — amount_items.unit 은 String(30) 이라
          인월 말고 식·건·개·㎡·월 도 온다. "(1인/한달)" 로 박아 두면 식 항목에서
          거짓이 된다. 데이터의 단위를 그대로 넣는다. */}
      <span className="precedent-item__unit">
        {formatMoney(item.unit_price)} 원
        {item.unit && <small>(1{item.unit} 단가)</small>}
      </span>

      {/* 수량을 그대로 뿌리면 안 된다. quantity 가 Numeric(18,4) 라서 서버가
          "3.0000" 을 보내는데 화면에 그대로 나오면 **3000 으로 읽힌다**
          (실제로 그렇게 읽었다). formatMoney 가 뜻 없는 소수점 뒤 0 을 뗀다.

          "3인 기준" 이라고 쓰지 않는다. 3인월은 3명x1개월 일 수도 1명x3개월 일
          수도 있어서 **사람 수를 알 수 없다.** 단위를 그대로 두어 "3인월 기준"
          으로 쓴다 — 모르는 것을 단정하지 않는다. */}
      {item.quantity && <span className="precedent-item__total">
        {formatMoney(item.quantity)}{item.unit ?? ''} 기준
        {item.amount ? <b> {formatMoney(item.amount)}</b> : <i className="precedent-item__none"> 총액 없음</i>}
      </span>}

      <span className="precedent-item__meta">
        {category ? category : <i className="precedent-item__none">원가구분 미판별</i>}
      </span>
      <span className="precedent-item__decision">{DECISION_LABELS[item.decision] ?? item.decision}</span>
    </div>
  </li>
}

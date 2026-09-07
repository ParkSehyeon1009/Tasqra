import { useState } from 'react'
import DecisionScheduleReviewPanel from './DecisionScheduleReviewView'
import TaskSuggestionReviewPanel from './TaskSuggestionReviewView'
import './DecisionScheduleReviewView.css'

// 두 검토 패널을 **세로로 쌓지 않고 전환**한다.
//
// 왜: 과업지시서 한 건에서 액션 태스크 후보가 20건 넘게 나온다. 그것을 다 그린
//   아래에 결정사항·일정 패널이 붙으면 **화면 밖으로 밀려 보이지 않는다.**
//   실제로 사용자가 결정사항 패널을 못 찾았다.
//
// ⚠️ 안쪽에도 탭이 있다(승인 대기·반영됨·거절됨). 두 층이 겹치므로 생김새를
//   다르게 뒀다 — 바깥은 칸을 나눈 전환기, 안쪽은 알약 모양이다. 같은 모양이면
//   어느 것이 무엇을 바꾸는지 알 수 없다.
const PANELS = [
  { key: 'task', label: '액션 태스크 후보', Panel: TaskSuggestionReviewPanel },
  { key: 'decision', label: '결정사항·일정', Panel: DecisionScheduleReviewPanel },
]

export default function AnalysisSidePanels(props) {
  const [active, setActive] = useState('task')
  const current = PANELS.find(p => p.key === active) ?? PANELS[0]
  const Panel = current.Panel
  return <div className='side-panel-switch'>
    <nav className='side-panel-switch__tabs' aria-label='검토 패널 전환'>
      {PANELS.map(panel => <button
        type='button'
        key={panel.key}
        className={active === panel.key ? 'is-active' : ''}
        aria-pressed={active === panel.key}
        onClick={() => setActive(panel.key)}
      >{panel.label}</button>)}
    </nav>
    {/* ⚠️ 두 패널을 **동시에 그리지 않는다.** 숨기기만 하면 안 보이는 쪽도
        계속 조회를 돌려 로컬 GPU 에 요청이 겹친다. */}
    <Panel {...props} />
  </div>
}

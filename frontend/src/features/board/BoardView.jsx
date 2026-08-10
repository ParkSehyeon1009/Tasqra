import PageHeading from '../../components/common/PageHeading'

export default function BoardView() {
  return <><PageHeading eyebrow="TASK BOARD" title="보드" description="AI 제안을 승인하면 프로젝트 태스크로 등록됩니다."/><div className="board"><BoardColumn title="TODO"/><BoardColumn title="DOING"/><BoardColumn title="DONE"/></div></>
}

function BoardColumn({ title }) {
  return <section><div><strong>{title}</strong><span>0</span></div><p>태스크 기능 연결 후 표시됩니다.</p></section>
}

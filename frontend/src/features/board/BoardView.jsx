import PageHeading from '../../components/common/PageHeading'

export default function BoardView() {
  return <><PageHeading eyebrow='TASK BOARD' title='보드' description='분석 결과에서 생성된 태스크가 이곳에 표시됩니다.'/>
    <section className='board-empty-state' role='status'><div className='board-empty-icon' aria-hidden='true'>□</div><div><h2>현재 등록된 태스크가 없습니다.</h2><p>이 프로젝트에는 표시할 태스크 데이터가 아직 없습니다. 분석 결과에서 태스크가 생성되는 경우 보드에 자동으로 표시됩니다.</p><small>태스크 생성과 분석 로직은 이 화면에서 변경하지 않습니다.</small></div></section>
  </>
}

export default function LoadingState({ label = '불러오는 중...' }) {
  return <div className="loading-state"><span/><p>{label}</p></div>
}

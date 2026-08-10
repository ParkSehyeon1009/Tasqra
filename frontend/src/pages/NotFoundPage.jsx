import { Link } from 'react-router-dom'
import Logo from '../components/common/Logo'

export default function NotFoundPage() {
  return <main className="not-found"><Logo/><h1>페이지를 찾을 수 없습니다.</h1><p>주소가 변경됐거나 존재하지 않는 페이지입니다.</p><Link className="primary" to="/">처음으로 돌아가기</Link></main>
}

import { Link } from 'react-router-dom'
import Logo from '../components/common/Logo'

export default function NotFoundPage() {
  return <main className='not-found recovery-page'><Logo/><p className='eyebrow'>PAGE NOT FOUND</p><h1>페이지를 찾을 수 없습니다.</h1><p>주소가 바뀌었거나 더 이상 접근할 수 없는 페이지일 수 있습니다.</p><div className='recovery-actions'><Link to='/projects'>내 프로젝트로 이동</Link><Link className='secondary-link' to='/'>홈으로 이동</Link></div></main>
}

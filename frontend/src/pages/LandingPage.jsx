import { Link } from 'react-router-dom'
import AppHeader from '../components/common/AppHeader'
import Logo from '../components/common/Logo'
import '../styles/landing.css'

const FEATURES = [['01','프로젝트 문서 관리','프로젝트별로 문서를 모으고 구성원의 접근 권한을 관리합니다.'],['02','OCR 검수','원본 위치와 추출 텍스트를 비교하고 수정해 결과를 검수합니다.'],['03','AI 액션 아이템','문서에서 할 일과 일정을 추출하고 승인 후 실제 작업으로 연결합니다.']]

export default function LandingPage({ user, onLogout, notify }) {
  return <div className="landing"><AppHeader user={user} onLogout={onLogout} notify={notify}/><main>
    <section className="hero"><p className="eyebrow">DOCUMENT TO PROJECT</p><h1>문서를 올리면<br/>프로젝트가 정리됩니다.</h1><p>OCR과 AI가 문서를 읽고, 함께 검수한 결과를 프로젝트의 실행 가능한 작업으로 연결합니다.</p><div><a className="primary" href="#features">기능 둘러보기</a><Link className="secondary" to={user ? '/projects' : '/login'} state={!user ? { loginRequired: true } : undefined}>{user ? '내 프로젝트 열기' : '작업 공간 열기'}</Link></div></section>
    <section id="features" className="feature-section"><div className="section-title"><p className="eyebrow">CORE FEATURES</p><h2>Tasqra에서 할 수 있는 일</h2></div><div className="feature-grid">{FEATURES.map(([number,title,description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></section>
    <section className="login-cta"><div><p className="eyebrow">PROJECT WORKSPACE</p><h2>{user ? `${user.name}님, 프로젝트 작업을 이어가세요.` : '프로젝트 작업을 시작하려면 로그인이 필요합니다.'}</h2><p>{user ? '참여 중인 프로젝트와 새 초대를 확인할 수 있습니다.' : '계정으로 로그인하거나 새 계정을 만든 뒤 문서 작업을 시작하세요.'}</p></div><div><Link className="primary" to={user ? '/projects' : '/login'} state={!user ? { loginRequired: true } : undefined}>{user ? '내 프로젝트' : '로그인하고 시작하기'}</Link>{!user && <Link className="secondary" to="/signup">회원가입</Link>}</div></section>
  </main><footer><Logo/><span>문서 기반 프로젝트 작업 도구</span></footer></div>
}

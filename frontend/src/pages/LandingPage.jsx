import { Link } from 'react-router-dom'
import Logo from '../components/common/Logo'
import '../styles/landing.css'

const FEATURES = [
  ['01', '프로젝트 문서 관리', '프로젝트별로 문서를 모으고 구성원의 접근 권한을 관리합니다.'],
  ['02', 'OCR 검수', '원본 위치와 추출 텍스트를 비교하고 팀이 함께 결과를 검수합니다.'],
  ['03', 'AI 액션 아이템', '문서에서 할 일과 일정을 추출하고 승인 후 태스크로 연결합니다.'],
]

export default function LandingPage() {
  return <div className="landing"><header className="landing-header"><Logo/><nav><a href="#features">기능</a><Link to="/login">로그인</Link><Link className="primary" to="/signup">무료로 시작하기</Link></nav></header>
    <main><section className="hero"><p className="eyebrow">DOCUMENT TO PROJECT</p><h1>문서를 올리면<br/>프로젝트가 정리됩니다.</h1><p>OCR과 AI가 문서를 읽고, 팀이 검수한 결과를 프로젝트의 실행 가능한 작업으로 연결합니다.</p><div><a className="primary" href="#features">기능 살펴보기</a><Link className="secondary" to="/login" state={{ loginRequired: true }}>작업 공간 열기</Link></div></section>
      <section id="features" className="feature-section"><div className="section-title"><p className="eyebrow">CORE FEATURES</p><h2>Tasqra에서 할 수 있는 일</h2></div><div className="feature-grid">{FEATURES.map(([number,title,description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></section>
      <section className="login-cta"><div><p className="eyebrow">PROJECT WORKSPACE</p><h2>프로젝트 작업을 시작하려면 로그인이 필요합니다.</h2><p>계정으로 로그인하거나 새 계정을 만들어 팀의 문서 작업을 시작하세요.</p></div><div><Link className="primary" to="/login" state={{ loginRequired: true }}>로그인하고 시작하기</Link><Link className="secondary" to="/signup">회원가입</Link></div></section>
    </main><footer><Logo/><span>문서 기반 프로젝트 협업 도구</span></footer></div>
}

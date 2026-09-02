// =============================================================================
// 이 파일의 책임: 승인된 메인 히어로 목업을 실제 공개 랜딩으로 제공한다.
// 다른 파일과의 관계: AppHeader와 로그인·회원가입 라우트, public/hero-flow.jpg를 쓴다.
// Spring 비교: 인증 없이 접근 가능한 제품 소개 Controller View에 해당한다.
// =============================================================================

import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import AppHeader from '../components/common/AppHeader'
import '../styles/landing.css'

const TRUST_ITEMS = [
  ['link', '원문 근거 연결'],
  ['document-check', 'OCR 결과 직접 검수'],
  ['people', '프로젝트별 팀 권한'],
  ['clock', '검토 이력 기록'],
]

const FEATURES = [
  ['document', '정확한 OCR', '다양한 형식의 문서를 높은 정확도로 인식'],
  ['sparkle', 'AI 문서 분석', '핵심 내용과 요구사항을 자동으로 추출'],
  ['grid', '프로젝트 자동 생성', '분석 결과를 바탕으로 프로젝트와 태스크 구성'],
  ['people', '협업 및 추적 관리', '진행 상황을 한눈에 확인하고 효율적으로 업무'],
]

const STEPS = [
  ['01', '문서를 정확하게 읽고', 'PDF, 이미지, DOCX, HWPX 문서의 텍스트를 추출하고 원문과 나란히 검수합니다.'],
  ['02', '핵심을 구조화하고', 'AI 분석 결과에서 핵심 요약, 요구사항, 금액과 일정을 프로젝트 정보로 정리합니다.'],
  ['03', '실행까지 연결합니다', '승인된 항목을 태스크로 관리하고 검토 결과를 다양한 형식의 산출물로 만듭니다.'],
]

export default function LandingPage({ user, onLogout, notify }) {
  useEffect(() => {
    const elements = [...document.querySelectorAll('.landing .reveal')]
    if (!('IntersectionObserver' in window)) {
      elements.forEach(element => element.classList.add('is-visible'))
      return undefined
    }
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return
        entry.target.classList.add('is-visible')
        observer.unobserve(entry.target)
      })
    }, { threshold: 0.14 })
    elements.forEach(element => observer.observe(element))
    return () => observer.disconnect()
  }, [])

  return <div className="landing motion-ready">
    <AppHeader user={user} onLogout={onLogout} notify={notify}/>
    <main className="landing-page">
      <section className="landing-hero">
        <div className="landing-hero__copy">
          <p className="eyebrow">DOCUMENT INTELLIGENCE WORKSPACE</p>
          <h1>복잡한 문서를<br/>명확한 <strong>실행으로</strong></h1>
          <p className="landing-hero__description">AI가 문서의 핵심을 분석하고,<br/>프로젝트와 태스크로 전환해 실행까지 지원합니다.</p>
          <div className="landing-hero__actions">
            <Link className="primary" to={user ? '/projects' : '/signup'}>{user ? '내 대시보드 열기' : '무료로 시작하기'}<Arrow/></Link>
            <a className="secondary" href="#workflow">작동 방식 보기</a>
          </div>
          <div className="landing-hero__notes" aria-label="주요 장점"><span>원문 근거 연결</span><span>프로젝트별 권한</span><span>검토 이력 기록</span></div>
        </div>
        <HeroFlow/>
      </section>

      <section className="landing-trust reveal" aria-label="신뢰 기능">
        {TRUST_ITEMS.map(([icon, label]) => <div key={label}><i aria-hidden="true"><LandingIcon name={icon}/></i><span>{label}</span></div>)}
      </section>

      <section id="features" className="landing-features reveal">
        <h2>Tasqra의 핵심 기능</h2>
        <div className="landing-feature-grid">{FEATURES.map(([icon, title, description]) => <article key={title}><span><LandingIcon name={icon}/></span><div><h3>{title}</h3><p>{description}</p></div></article>)}</div>
      </section>

      <section id="workflow" className="landing-workflow reveal">
        <div className="landing-section-heading"><p className="eyebrow">ONE CONNECTED WORKFLOW</p><h2>문서를 읽는 순간부터 실행까지,<br/>하나의 흐름으로 연결합니다.</h2><p>OCR 검수부터 AI 분석, 태스크 관리와 산출물 생성까지 끊김 없이 이어집니다.</p></div>
        <div className="landing-step-grid">{STEPS.map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div>
      </section>
    </main>
  </div>
}

function HeroFlow() {
  return <div className="hub-image">
    <div className="hub-art">
      <img src="/hero-flow.jpg" alt="문서 분석이 프로젝트 생성, 태스크와 일정 생성, 핵심 요약으로 이어지는 Tasqra 흐름"/>
      <span className="t-light" aria-hidden="true"/>
      <span className="t-orbit" aria-hidden="true"/>
    </div>
  </div>
}

function Arrow() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>
}

function LandingIcon({ name }) {
  const props = { viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', strokeWidth:2, strokeLinecap:'round', strokeLinejoin:'round', 'aria-hidden':true }
  if (name === 'link') return <svg {...props}><path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1"/></svg>
  if (name === 'document-check') return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="m9 15 2 2 4-5"/></svg>
  if (name === 'people') return <svg {...props}><circle cx="9" cy="8" r="3"/><path d="M3 20c0-3 2.7-5 6-5s6 2 6 5"/><circle cx="17" cy="9" r="2.4"/><path d="M16 15c2.5 0 5 1.6 5 5"/></svg>
  if (name === 'clock') return <svg {...props}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
  if (name === 'sparkle') return <svg {...props}><path d="M9.9 15.5A2 2 0 0 0 8.5 14.1l-6.1-1.6a.5.5 0 0 1 0-1L8.5 9.9A2 2 0 0 0 9.9 8.5l1.6-6.1a.5.5 0 0 1 1 0l1.6 6.1a2 2 0 0 0 1.4 1.4l6.1 1.6a.5.5 0 0 1 0 1l-6.1 1.6a2 2 0 0 0-1.4 1.4l-1.6 6.1a.5.5 0 0 1-1 0z"/></svg>
  if (name === 'grid') return <svg {...props}><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>
  return <svg {...props}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M9 15h1M14 15h1M9 11h1M14 11h1"/></svg>
}

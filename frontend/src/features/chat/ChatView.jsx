// =============================================================================
// 이 파일의 책임: 프로젝트 화면 어디서든 우측 하단 버튼으로 여는 문서 질의응답
//   패널을 제공하고, 같은 프로젝트의 최근 질문·답변 20개와 검증된 근거를 표시한다.
// 다른 파일과의 관계: App의 프로젝트 공통 호스트가 프로젝트별로 한 번 마운트하고
//   api/chat.js만 호출한다. 근거를 누르면 기존 문서 원문 화면의 해당 청크 구간으로 이동한다.
// Spring 비교: 전역 레이아웃 Widget View에 세션 한정 Command 결과 목록을 둔 형태다.
// =============================================================================

import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { askProjectDocuments } from '../../api/chat'
import './ChatView.css'

const MAX_CHAT_EXCHANGES = 20

export default function ChatView({ projectId, projectName }) {
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [exchanges, setExchanges] = useState([])
  const bodyRef = useRef(null)
  const inputRef = useRef(null)
  const nextExchangeIdRef = useRef(1)
  const navigate = useNavigate()
  const chat = useMutation({
    mutationFn: ({ question: value }) => askProjectDocuments(projectId, value),
  })

  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = event => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    window.setTimeout(() => inputRef.current?.focus(), 0)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  useEffect(() => {
    if (!open || !bodyRef.current) return
    bodyRef.current.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' })
  }, [open, exchanges])

  function updateExchange(exchangeId, update) {
    setExchanges(current => current.map(exchange =>
      exchange.id === exchangeId ? { ...exchange, ...update } : exchange
    ))
  }

  function submit(event) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || chat.isPending) return
    const exchangeId = nextExchangeIdRef.current++
    setExchanges(current => [
      ...current,
      { id: exchangeId, question: trimmed, status: 'pending' },
    ].slice(-MAX_CHAT_EXCHANGES))
    setQuestion('')
    chat.mutate(
      { exchangeId, question: trimmed },
      {
        onSuccess: response => updateExchange(exchangeId, {
          status: 'completed',
          response,
        }),
        onError: error => updateExchange(exchangeId, {
          status: 'failed',
          errorMessage: error?.message || '알 수 없는 오류가 발생했습니다.',
          errorCode: error?.code || '',
        }),
      },
    )
  }

  function openEvidence(item) {
    const target = `/projects/${item.project_id}/documents/${item.document_id}`
    setOpen(false)
    if (item.content_start === null || item.content_end === null) {
      navigate(target)
      return
    }
    const params = new URLSearchParams({
      tab: 'content',
      from: String(item.content_start),
      to: String(item.content_end),
    })
    navigate(`${target}?${params.toString()}`)
  }

  return <div className={`chat-widget${open ? ' is-open' : ''}`}>
    {open && <button type='button' className='chat-widget-backdrop' aria-label='챗봇 닫기' onClick={() => setOpen(false)}/>}

    <button type='button' className='chat-launcher' aria-expanded={open}
      aria-controls='project-chat-panel' onClick={() => setOpen(value => !value)}>
      {open ? <CloseIcon/> : <ChatIcon/>}
      <span>{open ? '닫기' : '문서에 질문'}</span>
    </button>

    {open && <aside id='project-chat-panel' className='chat-drawer' role='dialog'
      aria-modal='true' aria-labelledby='project-chat-title'>
      <header className='chat-drawer-header'>
        <div className='chat-drawer-symbol'><ChatIcon/></div>
        <div>
          <strong id='project-chat-title'>문서 챗봇</strong>
          <span>{projectName || '현재 프로젝트'}</span>
        </div>
        <button type='button' className='chat-drawer-close' aria-label='챗봇 닫기'
          onClick={() => setOpen(false)}><CloseIcon/></button>
      </header>

      <div className='chat-drawer-body' ref={bodyRef}>
        <div className='chat-intro'>
          <strong>프로젝트 문서를 근거로 답합니다.</strong>
          <p>답변에 사용한 문서와 원문 인용을 함께 확인할 수 있습니다.</p>
        </div>

        {exchanges.map(exchange => <div className='chat-exchange' key={exchange.id}>
          <div className='chat-message chat-message--user'>
            <span>나</span><p>{exchange.question}</p>
          </div>

          {exchange.status === 'pending' && <div className='chat-message chat-message--assistant'>
            <span>문서 챗봇</span><p className='chat-thinking'>관련 문서를 찾고 답변을 만들고 있습니다…</p>
          </div>}

          {exchange.status === 'failed' && <div className='chat-message chat-message--assistant chat-message--error'>
            <span>문서 챗봇</span>
            <p>답변을 만들지 못했습니다.</p>
            <small>{exchange.errorMessage}{exchange.errorCode ? ` · ${exchange.errorCode}` : ''}</small>
          </div>}

          {exchange.status === 'completed' && <ChatAnswer response={exchange.response} onOpen={openEvidence}/>}
        </div>)}
      </div>

      <form className='chat-composer' onSubmit={submit}>
        <label className='sr-only' htmlFor='chat-question'>프로젝트 문서에 질문하기</label>
        <textarea ref={inputRef} id='chat-question' value={question} maxLength={1000} rows={2}
          onChange={event => setQuestion(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit(event)
            }
          }}
          placeholder='프로젝트 문서에 질문해 보세요.'/>
        <button type='submit' aria-label='질문 보내기' disabled={!question.trim() || chat.isPending}>
          <SendIcon/>
        </button>
        <small>Enter 전송 · Shift+Enter 줄바꿈</small>
      </form>
    </aside>}
  </div>
}

function ChatAnswer({ response, onOpen }) {
  return <div className='chat-message chat-message--assistant' aria-live='polite'>
    <span>문서 챗봇</span>
    <p>{response.answer}</p>
    {response.evidence.length > 0 ? <div className='chat-citations'>
      <strong>근거 문서와 원문 인용</strong>
      <ol>
        {response.evidence.map(item => <li key={item.evidence_id}>
          <button type='button' onClick={() => onOpen(item)}>
            <b>[근거 {item.evidence_id}] {item.document_filename}</b>
            <span>{item.page_number ? `${item.page_number}쪽 · ` : ''}조각 {item.seq + 1}번</span>
            <blockquote>{item.quote}</blockquote>
          </button>
        </li>)}
      </ol>
    </div> : <small>답변에 사용된 문서 근거가 없습니다.</small>}
    <small className='chat-budget'>근거 예산 {response.evidence_used_tokens}/{response.evidence_budget_tokens} · {response.token_count_is_exact ? '정확 계산' : '보수적 근사'}</small>
  </div>
}

function ChatIcon() {
  return <svg width='22' height='22' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.8' aria-hidden='true'>
    <path d='M4 4.5h16v11H9l-5 4v-4H4z'/><path d='M8 9h8M8 12h5'/>
  </svg>
}

function CloseIcon() {
  return <svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' aria-hidden='true'>
    <path d='m6 6 12 12M18 6 6 18'/>
  </svg>
}

function SendIcon() {
  return <svg width='19' height='19' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.9' aria-hidden='true'>
    <path d='m3 11 17-8-6 18-3-7z'/><path d='m11 14 9-11'/>
  </svg>
}

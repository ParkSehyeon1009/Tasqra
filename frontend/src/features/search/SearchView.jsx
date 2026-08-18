// =============================================================================
// 이 파일의 책임: 의미 검색 화면(VIS-07)이다. 질의를 받아 api/search.js 를 부르고
//   결과를 목록으로 보여준다. 결과마다 출처 문서와 원문 인용이 함께 나온다
//   (RAG-08 = SRH-002-2 근거 스니펫).
//
// 다른 파일과의 관계: pages/WorkspacePage.jsx 의 TabContent 가 tab === 'search'
//   일 때 이것을 그린다. api/search.js 만 부르고 axios·경로는 모른다.
//
// 검색 범위를 토글로 두는 이유
//   기능명세서가 RAG-04(=SRH-001)에 "다른 프로젝트 문서는 나오지 않는다"고 쓰고,
//   RAG-12(=SRH-002-3)에 "과거 사업 문서에서 단가를 찾는다"고 쓴다. 과거 사업은
//   다른 프로젝트이므로 앞 문장을 문자 그대로 읽으면 두 기능이 서로를 부정한다.
//   "내가 멤버가 아닌 프로젝트"로 읽으면 둘 다 만족하고, 그때 사용자에게는
//   "이 프로젝트만" 과 "내 프로젝트 전체" 를 고를 수단이 필요해진다.
//
//   API 는 project_ids 목록을 받으므로, 나중에 프로젝트별 다중선택으로 바꿔도
//   서버를 고치지 않는다.
//
// Spring 비교: Thymeleaf 뷰 + 컨트롤러 대신 React 컴포넌트가 상태를 들고 있고,
//   서버 호출은 api/search.js(Gateway)로 분리했다.
// =============================================================================

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeading from '../../components/common/PageHeading'
import LoadingState from '../../components/common/LoadingState'
import { FAKE_EMBEDDING_MODEL, searchDocuments } from '../../api/search'
import './SearchView.css'

// 한 번에 가져올 결과 수. 서버 상한은 50 이다(schemas/search.py MAX_SEARCH_LIMIT).
const RESULT_LIMIT = 20

export default function SearchView({ projectId, projectName }) {
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState('project')   // 'project' | 'all'
  const [response, setResponse] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  // 마지막으로 실제 검색한 조건. 입력만 바꾸고 검색하지 않았을 때
  // "결과 없음" 문구가 엉뚱하게 바뀌는 것을 막는다.
  const [lastQuery, setLastQuery] = useState('')
  const navigate = useNavigate()

  async function runSearch(event) {
    event?.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || loading) return

    setLoading(true)
    setError(null)
    try {
      const data = await searchDocuments({
        query: trimmed,
        // 'all' 이면 범위를 보내지 않는다 -> 서버가 내 멤버십 전체로 푼다.
        projectIds: scope === 'project' ? [Number(projectId)] : null,
        limit: RESULT_LIMIT,
      })
      setResponse(data)
      setLastQuery(trimmed)
    } catch (caught) {
      setError(caught)
      setResponse(null)
    } finally {
      setLoading(false)
    }
  }

  function openDocument(result) {
    navigate(`/projects/${result.project_id}/documents/${result.document_id}`)
  }

  const isFake = response?.embedding_model === FAKE_EMBEDDING_MODEL

  return <>
    <PageHeading
      eyebrow='SEMANTIC SEARCH'
      title='검색'
      description='글자가 정확히 겹치지 않아도 뜻이 비슷한 내용을 찾습니다. 결과마다 출처 문서와 원문 인용이 함께 나옵니다.'/>

    <section className='panel search-panel'>
      <form className='search-form' onSubmit={runSearch}>
        <input
          className='search-input'
          type='search'
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder='예: 대금은 언제 받을 수 있나요'
          maxLength={1000}
          aria-label='검색어'/>
        <button className='primary' type='submit' disabled={loading || !query.trim()}>
          {loading ? '검색 중...' : '검색'}
        </button>
      </form>

      <ScopeToggle scope={scope} projectName={projectName} disabled={loading} onChange={setScope}/>
    </section>

    {isFake && <FakeEmbeddingNotice/>}

    {loading && <LoadingState label='비슷한 내용을 찾는 중...'/>}

    {error && !loading && <section className='panel search-error'>
      <p><strong>검색에 실패했습니다.</strong></p>
      <p>{error.message}</p>
      {error.code && <p className='search-error-code'>코드 {error.code}</p>}
    </section>}

    {response && !loading && !error && <SearchResults
      response={response}
      lastQuery={lastQuery}
      currentProjectId={Number(projectId)}
      onOpen={openDocument}/>}
  </>
}

function ScopeToggle({ scope, projectName, disabled, onChange }) {
  return <div className='search-scope' role='group' aria-label='검색 범위'>
    <button
      type='button'
      className={scope === 'project' ? 'active' : ''}
      disabled={disabled}
      onClick={() => onChange('project')}>
      이 프로젝트만
    </button>
    <button
      type='button'
      className={scope === 'all' ? 'active' : ''}
      disabled={disabled}
      onClick={() => onChange('all')}>
      내 프로젝트 전체
    </button>
    <p className='search-scope-hint'>
      {scope === 'project'
        ? <>{projectName ? `"${projectName}"` : '현재 프로젝트'} 안에서만 찾습니다.</>
        : '내가 멤버인 프로젝트에서 찾습니다. 멤버가 아닌 프로젝트는 결과에 나오지 않습니다.'}
    </p>
  </div>
}

// 개발 기본값이 가짜 임베더(USE_FAKE_EMBEDDING=true)라서, 그 상태를 화면에
// 알려야 한다. 알리지 않으면 "검색이 왜 엉뚱한 걸 주지"로 시간을 버린다.
function FakeEmbeddingNotice() {
  return <section className='panel search-notice'>
    <p><strong>개발용 가짜 임베딩으로 검색했습니다.</strong></p>
    <p>
      벡터가 텍스트 해시로 만들어져 <b>의미가 없습니다.</b> 순서와 유사도 값에
      뜻을 두지 마세요. 검색이 동작하는지(권한·범위·응답 형식)만 확인할 수 있습니다.
    </p>
    <p className='search-notice-how'>
      실제 모델로 바꾸려면 서버에서 <code>USE_FAKE_EMBEDDING=false</code> 로 두고
      임베딩 서버를 연결해야 합니다.
    </p>
  </section>
}

function SearchResults({ response, lastQuery, currentProjectId, onOpen }) {
  const { results, total, took_ms, searched_project_ids } = response
  // 범위가 여러 프로젝트면 결과마다 프로젝트 이름을 보여야 한다. 한 곳이면
  // 모든 줄에 같은 이름이 반복되어 시선만 방해한다.
  const showProject = searched_project_ids.length > 1

  if (!results.length) {
    return <section className='panel search-empty'>
      <p><strong>"{lastQuery}" 와 비슷한 내용을 찾지 못했습니다.</strong></p>
      <p>
        문서가 아직 처리되지 않았을 수 있습니다. 업로드 직후에는 청킹과 임베딩이
        끝나야 검색에 걸립니다. 범위를 <b>내 프로젝트 전체</b>로 넓혀 보세요.
      </p>
      <p className='search-meta'>검색한 프로젝트 {searched_project_ids.length}곳 · {took_ms}ms</p>
    </section>
  }

  return <section className='panel search-results'>
    <div className='panel-head'>
      <div>
        <h2>검색 결과</h2>
        <p>"{lastQuery}" 와 뜻이 가까운 순서입니다.</p>
      </div>
      <span>{total}건</span>
    </div>

    <p className='search-meta'>
      프로젝트 {searched_project_ids.length}곳에서 {took_ms}ms
      {response.embedding_model && <> · 모델 <code>{response.embedding_model}</code></>}
    </p>

    <ol className='search-result-list'>
      {results.map(result => <ResultRow
        key={result.chunk_id}
        result={result}
        showProject={showProject}
        isOtherProject={result.project_id !== currentProjectId}
        onOpen={onOpen}/>)}
    </ol>
  </section>
}

function ResultRow({ result, showProject, isOtherProject, onOpen }) {
  // 유사도는 0~1 이 정상 범위다. 백분율로 보여 주면 읽기 쉽다.
  const percent = Math.round(result.similarity * 100)
  // snippet 이 잘렸는지는 char_count 와 비교해 안다 (서버가 220자로 자른다).
  const truncated = result.char_count > result.snippet.length

  return <li className='search-result'>
    <button type='button' className='search-result-body' onClick={() => onOpen(result)}>
      <div className='search-result-head'>
        <span className='search-result-file'>{result.document_filename}</span>
        {showProject && <span className={'search-result-project' + (isOtherProject ? ' is-other' : '')}>
          {result.project_name}
        </span>}
      </div>

      <p className='search-result-snippet'>
        {result.snippet}{truncated && <span className='search-result-more'> …</span>}
      </p>

      <div className='search-result-meta'>
        <span title='코사인 유사도'>유사도 {percent}%</span>
        {result.page_number !== null && result.page_number !== undefined && <span>{result.page_number}쪽</span>}
        <span>조각 {result.seq + 1}번</span>
        <span>{result.char_count}자</span>
      </div>
    </button>
  </li>
}

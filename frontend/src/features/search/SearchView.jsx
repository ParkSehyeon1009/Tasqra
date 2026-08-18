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

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import PageHeading from '../../components/common/PageHeading'
import LoadingState from '../../components/common/LoadingState'
import { FAKE_EMBEDDING_MODEL, searchDocuments } from '../../api/search'
import './SearchView.css'

// 한 번에 가져올 결과 수. 서버 상한은 50 이다(schemas/search.py MAX_SEARCH_LIMIT).
const RESULT_LIMIT = 20

// 검색 결과를 캐시에 얼마나 신선하게 둘지. 기본값(30초)보다 길게 잡는다.
// 문서를 열어 보고 뒤로 돌아오는 데 30초가 넘게 걸리는 일이 흔하고, 그때마다
// 다시 임베딩하면 질의당 300ms 를 또 쓴다.
const SEARCH_STALE_MS = 10 * 60 * 1000

export default function SearchView({ projectId, projectName }) {
  // 검색 조건을 URL 에 둔다. 그래야 문서를 열었다가 뒤로 와도 그대로 복원되고,
  // 새로고침·주소 공유도 된다. 컴포넌트 상태에만 두면 화면을 떠날 때 사라진다.
  const [params, setParams] = useSearchParams()
  const query = params.get('q') ?? ''
  const scope = params.get('scope') === 'all' ? 'all' : 'project'

  // 입력창은 로컬 상태다. 글자를 칠 때마다 URL 이 바뀌면 뒤로가기 이력이
  // 한 글자마다 쌓인다.
  const [draft, setDraft] = useState(query)
  const navigate = useNavigate()

  // 뒤로가기로 URL 이 바뀌면 입력창도 따라가게 한다.
  useEffect(() => { setDraft(query) }, [query])

  const search = useQuery({
    queryKey: ['semantic-search', String(projectId), query, scope],
    queryFn: () => searchDocuments({
      query,
      // 'all' 이면 범위를 보내지 않는다 -> 서버가 내 멤버십 전체로 푼다.
      projectIds: scope === 'project' ? [Number(projectId)] : null,
      limit: RESULT_LIMIT,
    }),
    // 질의가 없으면 요청하지 않는다.
    enabled: query.trim().length > 0,
    staleTime: SEARCH_STALE_MS,
    retry: false,
  })

  function submit(event) {
    event?.preventDefault()
    const trimmed = draft.trim()
    if (!trimmed) return
    // 같은 조건이면 URL 을 건드리지 않는다 (이력이 쌓이지 않게).
    if (trimmed === query) return
    setParams({ q: trimmed, scope })
  }

  function changeScope(next) {
    if (next === scope) return
    // 범위를 바꾸면 질의를 유지한 채 다시 검색한다.
    setParams(query ? { q: query, scope: next } : { scope: next })
  }

  function openChunk(result) {
    // 클릭한 조각이 원문에서 어디인지 넘긴다. DocumentContentTab 이 그 구간을
    // 강조하고 그 자리로 스크롤한다. 구간을 모르는 조각(긴 줄을 강제로 쪼갠
    // 경우)은 좌표가 null 이라 그냥 문서만 열린다.
    const target = `/projects/${result.project_id}/documents/${result.document_id}`
    if (result.content_start === null || result.content_end === null) {
      navigate(target)
      return
    }
    const search = new URLSearchParams({
      tab: 'content',
      from: String(result.content_start),
      to: String(result.content_end),
    })
    navigate(`${target}?${search.toString()}`)
  }

  const response = search.data
  const isFake = response?.embedding_model === FAKE_EMBEDDING_MODEL
  // 캐시된 결과를 다시 확인하는 중에는 결과를 그대로 두고 로딩을 띄우지 않는다.
  const loading = search.isPending && query.trim().length > 0

  return <>
    <PageHeading
      eyebrow='SEMANTIC SEARCH'
      title='검색'
      description='글자가 정확히 겹치지 않아도 뜻이 비슷한 내용을 찾습니다. 결과마다 출처 문서와 원문 인용이 함께 나옵니다.'/>

    <section className='panel search-panel'>
      <form className='search-form' onSubmit={submit}>
        <input
          className='search-input'
          type='search'
          value={draft}
          onChange={event => setDraft(event.target.value)}
          placeholder='예: 대금은 언제 받을 수 있나요'
          maxLength={1000}
          aria-label='검색어'/>
        <button className='primary' type='submit' disabled={loading || !draft.trim()}>
          {loading ? '검색 중...' : '검색'}
        </button>
      </form>

      <ScopeToggle scope={scope} projectName={projectName} disabled={loading} onChange={changeScope}/>
    </section>

    {isFake && <FakeEmbeddingNotice/>}

    {loading && <LoadingState label='비슷한 내용을 찾는 중...'/>}

    {search.isError && !loading && <section className='panel search-error'>
      <p><strong>검색에 실패했습니다.</strong></p>
      <p>{search.error?.message}</p>
      {search.error?.code && <p className='search-error-code'>코드 {search.error.code}</p>}
    </section>}

    {response && !loading && !search.isError && <SearchResults
      response={response}
      lastQuery={query}
      currentProjectId={Number(projectId)}
      onOpen={openChunk}/>}
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

// 문서 하나에서 펼쳐 보여줄 조각 수. 나머지는 접어 둔다.
// 긴 문서 하나가 목록을 독점하는 것을 막는 것이 목적이다 — 45,000자 문서면
// 상위 20개가 그 문서 조각으로만 채워질 수 있다.
const CHUNKS_SHOWN_PER_DOCUMENT = 2

/**
 * 결과를 문서별로 묶는다. 순서는 "그 문서의 가장 좋은 조각이 나온 순서"다.
 *
 * 서버가 문서가 아니라 조각을 돌려주는 것은 맞다 — 프롬프트 컨텍스트 조립
 * (RAG-07)은 같은 문서에서 여러 조각을 골라 넣어야 하고, 근거 인용(RAG-08)도
 * 조각 단위여야 의미가 있다. 묶는 것은 화면의 일이다.
 */
function groupByDocument(results) {
  const order = []
  const groups = new Map()
  for (const item of results) {
    let group = groups.get(item.document_id)
    if (!group) {
      group = {
        document_id: item.document_id,
        filename: item.document_filename,
        project_id: item.project_id,
        project_name: item.project_name,
        items: [],
      }
      groups.set(item.document_id, group)
      order.push(item.document_id)
    }
    group.items.push(item)
  }
  return order.map(id => groups.get(id))
}

function SearchResults({ response, lastQuery, currentProjectId, onOpen }) {
  const { results, total, took_ms, searched_project_ids } = response
  // 어느 문서를 펼쳤는지. document_id 를 담는다.
  const [expanded, setExpanded] = useState(() => new Set())
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

  const groups = groupByDocument(results)

  function toggle(documentId) {
    setExpanded(previous => {
      const next = new Set(previous)
      if (next.has(documentId)) next.delete(documentId)
      else next.add(documentId)
      return next
    })
  }

  return <section className='panel search-results'>
    <div className='panel-head'>
      <div>
        <h2>검색 결과</h2>
        <p>"{lastQuery}" 와 뜻이 가까운 순서입니다.</p>
      </div>
      {/* 조각 수만 세면 "문서 4개" 로 오해한다. 둘을 나눠 보여준다. */}
      <span>문서 {groups.length}개 · 조각 {total}건</span>
    </div>

    <p className='search-meta'>
      프로젝트 {searched_project_ids.length}곳에서 {took_ms}ms
      {response.embedding_model && <> · 모델 <code>{response.embedding_model}</code></>}
    </p>

    <ul className='search-doc-list'>
      {groups.map(group => <DocumentGroup
        key={group.document_id}
        group={group}
        showProject={showProject}
        isOtherProject={group.project_id !== currentProjectId}
        open={expanded.has(group.document_id)}
        onToggle={() => toggle(group.document_id)}
        onOpen={onOpen}/>)}
    </ul>
  </section>
}

function DocumentGroup({ group, showProject, isOtherProject, open, onToggle, onOpen }) {
  const shown = open ? group.items : group.items.slice(0, CHUNKS_SHOWN_PER_DOCUMENT)
  const hidden = group.items.length - shown.length
  // 문서의 대표 유사도는 가장 좋은 조각 것이다. 서버가 거리 오름차순으로 주므로
  // 첫 조각이 가장 가깝다.
  const best = Math.round(group.items[0].similarity * 100)

  return <li className='search-doc'>
    <div className='search-doc-head'>
      <button
        type='button'
        className='search-doc-title'
        onClick={() => onOpen(group.items[0])}
        title='문서 상세로 이동'>
        {group.filename}
      </button>
      {showProject && <span className={'search-result-project' + (isOtherProject ? ' is-other' : '')}>
        {group.project_name}
      </span>}
      <span className='search-doc-count'>조각 {group.items.length}개 · 최고 {best}%</span>
    </div>

    <ol className='search-result-list'>
      {shown.map(item => <ResultRow key={item.chunk_id} result={item} onOpen={onOpen}/>)}
    </ol>

    {hidden > 0 && <button type='button' className='search-doc-more' onClick={onToggle}>
      이 문서에서 {hidden}건 더 보기
    </button>}
    {open && group.items.length > CHUNKS_SHOWN_PER_DOCUMENT && <button
      type='button' className='search-doc-more' onClick={onToggle}>
      접기
    </button>}
  </li>
}

function ResultRow({ result, onOpen }) {
  // 유사도는 0~1 이 정상 범위다. 백분율로 보여 주면 읽기 쉽다.
  const percent = Math.round(result.similarity * 100)
  // snippet 이 잘렸는지는 char_count 와 비교해 안다 (서버가 220자로 자른다).
  const truncated = result.char_count > result.snippet.length

  return <li className='search-result'>
    <button type='button' className='search-result-body' onClick={() => onOpen(result)}>
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

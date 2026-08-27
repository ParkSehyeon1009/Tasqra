// =============================================================================
// 이 파일의 책임: 의미 검색 화면(SRH-001)이다. 질의를 받아 api/search.js 를 부르고
//   결과를 목록으로 보여준다. 결과마다 출처 문서와 원문 인용이 함께 나온다
//   (SRH-002-2 근거 스니펫).
//
// 다른 파일과의 관계: pages/WorkspacePage.jsx 의 TabContent 가 tab === 'search'
//   일 때 이것을 그린다. api/search.js 만 부르고 axios·경로는 모른다.
//
// 검색 범위를 토글로 두는 이유
//   기능명세서가 SRH-001에 "다른 프로젝트 문서는 나오지 않는다"고 쓰고,
//   SRH-002-3에 "과거 사업 문서에서 단가를 찾는다"고 쓴다. 과거 사업은
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
import { FAKE_EMBEDDING_MODEL, searchHybrid } from '../../api/search'
import AmountPrecedentPanel from '../amount/AmountPrecedentPanel'
import './SearchView.css'

// 한 번에 가져올 결과 수. 서버 상한은 50 이다(schemas/search.py MAX_SEARCH_LIMIT).
const RESULT_LIMIT = 20

// 결과마다 "어떻게 찾았는지"(의미 / 키워드 / 둘 다)를 배지로 보여줄까.
//
// 켜 두는 이유는 검증이다 — 하이브리드가 정말 두 방식을 합치고 있는지, 키워드가
// 의미 검색이 놓친 것을 데려오는지 눈으로 확인할 수 있어야 한다. **백엔드는
// match_kind 를 계속 보내므로 이것을 false 로 바꿔도 API 로는 확인이 된다.**
//
// 사용자에게는 알고리즘이 필요한 정보가 아니다. 검증이 끝나면 false 로 둔다.
const SHOW_MATCH_KIND = true

// match_kind -> 배지 글자.
const MATCH_LABEL = { vector: '의미', keyword: '키워드', both: '의미+키워드' }

/**
 * 이 결과에 코사인 유사도가 있는가.
 *
 * similarity 필드의 뜻이 match_kind 에 따라 다르다 — 벡터로 걸렸으면 코사인
 * 유사도지만, 키워드만으로 걸렸으면 트라이그램 낱말 유사도다. 후자를
 * "유사도 87%" 로 보여주면 뜻이 다른 값을 같은 이름으로 부르는 것이 된다.
 *
 * match_kind 가 없으면(null) 의미 검색 응답이다 — /api/search 를 직접 부른
 * 경우이므로 코사인이 맞다.
 */
function hasCosine(item) {
  return !item.match_kind || item.match_kind === 'vector' || item.match_kind === 'both'
}

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
  // 무엇을 찾는지에 따라 화면이 갈린다. 문서 내용은 문장으로 찾고(의미 검색),
  // 단가 선례는 항목명으로 찾는다(SRH-002-3). 질의 형태와 결과 모양이 서로
  // 달라서 한 입력창에 합치면 둘 다 어색해진다.
  const [mode, setMode] = useState('content')
  const navigate = useNavigate()

  // 뒤로가기로 URL 이 바뀌면 입력창도 따라가게 한다.
  useEffect(() => { setDraft(query) }, [query])

  const search = useQuery({
    queryKey: ['hybrid-search', String(projectId), query, scope],
    queryFn: () => searchHybrid({
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
      description='문서 내용은 뜻이 비슷한 것과 글자가 그대로 있는 것을 함께 찾고, 단가는 과거 사업의 선례를 찾습니다. 결과마다 출처 문서와 원문 인용이 함께 나옵니다.'/>

    <div className='search-modes' role='tablist' aria-label='찾는 대상'>
      <button type='button' role='tab' aria-selected={mode === 'content'}
        className={mode === 'content' ? 'is-active' : ''} onClick={() => setMode('content')}>
        문서 내용
      </button>
      <button type='button' role='tab' aria-selected={mode === 'precedent'}
        className={mode === 'precedent' ? 'is-active' : ''} onClick={() => setMode('precedent')}>
        과거 단가 선례
      </button>
    </div>

    {mode === 'precedent' && <section className='panel search-panel search-panel--precedent'>
      <AmountPrecedentPanel projectId={projectId}/>
    </section>}

    {mode === 'content' && <>
    <section className='panel search-panel search-panel--content'>
      <form className='search-form' onSubmit={submit}>
        <input
          className='search-input'
          type='search'
          value={draft}
          onChange={event => setDraft(event.target.value)}
          placeholder='예: 대금은 언제 받을 수 있나요 / 제2026-403호'
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
    </>}
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
 * (RAG-002-1)은 같은 문서에서 여러 조각을 골라 넣어야 하고, 근거 인용(SRH-002-2)도
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
      <p><strong>"{lastQuery}" 에 해당하는 내용을 찾지 못했습니다.</strong></p>
      <p>
        뜻이 비슷한 내용과 글자가 그대로 있는 곳을 함께 찾았지만 없었습니다.
        문서가 아직 처리되지 않았을 수 있습니다 — 업로드 직후에는 청킹과 임베딩이
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
        {/* "뜻이 가까운 순서" 가 아니다. 뜻이 비슷한 것과 글자가 일치하는 것을
            합친 순위(RRF)라서, 둘 다 걸린 조각이 위로 온다. */}
        <p>"{lastQuery}" 와 관련이 높은 순서입니다.</p>
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
        lastQuery={lastQuery}
        onToggle={() => toggle(group.document_id)}
        onOpen={onOpen}/>)}
    </ul>
  </section>
}

function DocumentGroup({ group, showProject, isOtherProject, open, lastQuery, onToggle, onOpen }) {
  const shown = open ? group.items : group.items.slice(0, CHUNKS_SHOWN_PER_DOCUMENT)
  const hidden = group.items.length - shown.length
  // 문서의 대표 유사도.
  //
  // **하이브리드에서는 "첫 조각이 가장 가깝다" 가 성립하지 않는다.** 순서가
  // RRF 로 정해지므로 첫 조각은 "합친 순위가 가장 높은 것" 이고, 코사인
  // 유사도가 가장 높은 것이 아니다. 그래서 첫 조각 값을 쓰지 않고 코사인이
  // 있는 조각들 중 최대를 고른다.
  //
  // 코사인이 있는 조각이 없으면(전부 키워드로만 걸림) 표시하지 않는다.
  // 트라이그램 값을 "유사도" 로 부르면 뜻이 다른 값을 같은 이름으로 쓰게 된다.
  const cosines = group.items.filter(hasCosine).map(item => item.similarity)
  const best = cosines.length ? Math.round(Math.max(...cosines) * 100) : null

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
      <span className='search-doc-count'>
        조각 {group.items.length}개{best !== null && <> · 최고 {best}%</>}
      </span>
    </div>

    <ol className='search-result-list'>
      {shown.map(item => <ResultRow
        key={item.chunk_id} result={item} lastQuery={lastQuery} onOpen={onOpen}/>)}
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

/**
 * 스니펫에서 검색어가 나온 자리를 강조한다 (SRH-003).
 *
 * 서버가 match_offset 을 준다 — snippet 안에서 검색어가 시작하는 위치다.
 * 프론트에서 다시 찾지 않는 이유: 서버가 공백을 누른 뒤에 위치를 잡았으므로,
 * 여기서 다시 찾으면 규칙이 어긋날 수 있다. 준 값을 그대로 쓴다.
 *
 * 위치가 없으면(의미 검색으로만 걸린 결과) 그냥 글자를 돌려준다.
 */
function highlight(snippet, offset, term) {
  if (!term) return snippet

  // 서버가 준 offset 을 먼저 믿되, **정말 그 자리에 검색어가 있는지 확인한다.**
  //
  // ⚠ 단위가 다르다 — 서버(파이썬)는 글자를 **코드포인트**로 세고 브라우저(JS)는
  // **UTF-16 코드유닛**으로 센다. BMP 밖 문자(이모지 · 확장 한자 𠀋 같은 것)는
  // 파이썬 1글자 = JS 2글자다. 그런 문자가 검색어 앞에 하나 있으면 offset 이 1
  // 밀리고, 서로게이트 반쪽이 잘려 깨진 글자가 화면에 나온다. 실제로 재현했다.
  //
  // 조달 문서에 이모지는 드물지만 확장 한자는 인명·지명에 나올 수 있고 OCR
  // 오인식도 있다. 그래서 확인하고, 어긋나면 여기서 직접 찾는다.
  const at = usableOffset(snippet, offset, term)
  if (at === null) return snippet

  return <>
    {snippet.slice(0, at)}
    <mark className='search-result-hit'>{snippet.slice(at, at + term.length)}</mark>
    {snippet.slice(at + term.length)}
  </>
}

/**
 * 강조에 쓸 위치를 정한다. 못 정하면 null.
 *
 * 서버 offset -> 검증 -> 어긋나면 직접 찾기, 순서다.
 *
 * 직접 찾아도 결과가 같은 이유: 서버는 스니펫을 만들 때 **본문의 첫 번째 매치**를
 * 창 안에 담는다. 그래서 스니펫 안의 첫 매치가 곧 서버가 가리킨 그 자리다.
 * 서버 값을 먼저 쓰는 것은 규칙의 출처를 서버에 두려는 것이고, 직접 찾기는
 * 단위 차이를 메우는 안전망이다.
 */
function usableOffset(snippet, offset, term) {
  const lower = snippet.toLowerCase()
  const wanted = term.toLowerCase()

  if (typeof offset === 'number' && offset >= 0 && offset + term.length <= snippet.length) {
    if (lower.slice(offset, offset + term.length) === wanted) return offset
  }
  const found = lower.indexOf(wanted)
  return found >= 0 ? found : null
}

function ResultRow({ result, lastQuery, onOpen }) {
  // snippet 이 잘렸는지는 char_count 와 비교해 안다.
  const truncated = result.char_count > result.snippet.length
  const label = MATCH_LABEL[result.match_kind]
  const body = highlight(result.snippet, result.match_offset, lastQuery.trim())

  return <li className='search-result'>
    <button type='button' className='search-result-body' onClick={() => onOpen(result)}>
      <p className='search-result-snippet'>
        {body}{truncated && <span className='search-result-more'> …</span>}
      </p>

      <div className='search-result-meta'>
        {SHOW_MATCH_KIND && label && <span
          className={'search-result-kind is-' + result.match_kind}
          title='어떻게 찾았는지 (검증용 표시)'>{label}</span>}

        {/* 유사도는 코사인일 때만 백분율로 보여준다. 키워드로만 걸린 결과의
            similarity 는 트라이그램 값이라 뜻이 달라서 같은 이름을 쓸 수 없다. */}
        {hasCosine(result)
          ? <span title='코사인 유사도'>유사도 {Math.round(result.similarity * 100)}%</span>
          : null}

        {/* 키워드로 걸렸으면 몇 번 나왔는지가 더 쓸모 있는 신호다. */}
        {result.match_count > 0 && <span title='본문에 검색어가 나온 횟수'>
          {result.match_count}회 일치
        </span>}

        {result.page_number !== null && result.page_number !== undefined && <span>{result.page_number}쪽</span>}
        <span>조각 {result.seq + 1}번</span>
        <span>{result.char_count}자</span>
      </div>
    </button>
  </li>
}

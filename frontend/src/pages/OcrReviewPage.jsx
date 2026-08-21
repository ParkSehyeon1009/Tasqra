import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { useBlocker, useNavigate, useParams } from 'react-router-dom'
import { completeOcrReview, getDocument, getOcrPageImage, getOcrReview, setOcrElementExclusion, updateOcrElementsBatch } from '../api/document'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import { getReviewStatus } from '../utils/documentStatus'
import '../styles/ocr-review.css'
import '../styles/ocr-review-adjustments.css'
import '../styles/ocr-exclusion.css'

export default function OcrReviewPage({ user, onLogout, notify }) {
  const { projectId, documentId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [pageIndex, setPageIndex] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [structureDrafts, setStructureDrafts] = useState({})
  const [elementFilter, setElementFilter] = useState('ALL')
  const allowNavigationRef = useRef(false)
  const projectQuery = useQuery({ queryKey: ['project-access', projectId], queryFn: () => getProject(projectId), retry: false })
  const documentQuery = useQuery({ queryKey: ['projects', projectId, 'documents', documentId], queryFn: () => getDocument(projectId, documentId) })
  const reviewKey = ['projects', projectId, 'documents', documentId, 'ocr-review']
  const reviewQuery = useQuery({ queryKey: reviewKey, queryFn: () => getOcrReview(projectId, documentId) })
  const review = reviewQuery.data
  const pages = review?.pages ?? []
  const page = pages[pageIndex]
  const effectiveSelectedId = selectedId ?? page?.elements[0]?.id ?? null
  const selectedSource = useMemo(() => page?.elements.find(item => item.id === effectiveSelectedId) ?? null, [page, effectiveSelectedId])
  const selected = selectedSource ? { ...selectedSource, ...structureDrafts[selectedSource.id] } : null
  const draft = selected ? (drafts[selected.id] ?? selected.text) : ''
  const effectivePageElements = useMemo(() => page?.elements.map(element => ({ ...element, ...structureDrafts[element.id] })) ?? [], [page, structureDrafts])
  const lowConfidenceElements = useMemo(() => effectivePageElements.filter(element => confidenceLevel(element.confidence) === 'low'), [effectivePageElements])
  const canEdit = projectQuery.data?.role !== 'VIEWER'
  const dirtyChanges = pages.flatMap(item => item.elements.map(element => buildBatchChange(element, drafts[element.id], structureDrafts[element.id])).filter(Boolean))
  const hasUnsavedChanges = dirtyChanges.length > 0
  const totalElements = pages.reduce((count, item) => count + item.elements.length, 0)
  const changedElements = pages.reduce((count, item) => count + item.elements.filter(element => element.version > 1 || element.is_excluded).length, 0)
  const reviewStatus = getReviewStatus(review?.review_status)
  const blocker = useBlocker(({ currentLocation, nextLocation }) => hasUnsavedChanges && !allowNavigationRef.current && currentLocation.pathname !== nextLocation.pathname)


  useEffect(() => {
    const protectChanges = event => { if (hasUnsavedChanges) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', protectChanges)
    return () => window.removeEventListener('beforeunload', protectChanges)
  }, [hasUnsavedChanges])

  useEffect(() => {
    if (blocker.state !== 'blocked') return
    if (window.confirm('저장하지 않은 수정 내용이 있습니다. 이 페이지를 떠날까요?')) blocker.proceed()
    else blocker.reset()
  }, [blocker])

  function confirmDiscard(message) {
    return !hasUnsavedChanges || window.confirm(message)
  }

  function selectElement(element, moveToEditor = false) {
    if (element.id === effectiveSelectedId) return
    setSelectedId(element.id)
    if (moveToEditor) requestAnimationFrame(() => document.getElementById('ocr-element-' + element.id)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }

  function changePage(nextIndex) {
    if (nextIndex < 0 || nextIndex >= pages.length || nextIndex === pageIndex) return
    setPageIndex(nextIndex)
    setSelectedId(null)
  }

  function changeElementFilter(nextFilter) {
    setElementFilter(nextFilter)
    if (nextFilter === 'LOW' && !lowConfidenceElements.some(element => element.id === effectiveSelectedId)) {
      setSelectedId(lowConfidenceElements[0]?.id ?? null)
    }
  }

  function goBack() {
    if (!confirmDiscard('저장하지 않은 수정 내용이 있습니다. 문서 목록으로 돌아갈까요?')) return
    allowNavigationRef.current = true
    navigate('/projects/' + projectId + '/documents')
  }

  function updateStructure(element, patch) {
    setStructureDrafts(current => ({ ...current, [element.id]: { ...(current[element.id] ?? {}), ...patch } }))
  }

  function applyAutomaticParagraphs() {
    const suggestions = suggestParagraphStarts(effectivePageElements)
    setStructureDrafts(current => {
      const next = { ...current }
      effectivePageElements.forEach((element, index) => {
        if (index === 0 || isTableElement(element)) return
        const suggested = suggestions.get(element.id) ?? false
        if (suggested !== element.is_paragraph_start) next[element.id] = { ...(next[element.id] ?? {}), is_paragraph_start: suggested }
      })
      return next
    })
  }

  const updateMutation = useMutation({
    mutationFn: changes => updateOcrElementsBatch(projectId, documentId, changes),
    onSuccess: result => {
      const updatedById = new Map(result.items.map(element => [element.id, element]))
      queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: result.ocr_revision, review_status: 'IN_PROGRESS', pages: current.pages.map(item => ({ ...item, elements: item.elements.map(element => updatedById.get(element.id) ?? element) })) }) : current)
      setDrafts({})
      setStructureDrafts({})
      queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true })
      notify('success', 'OCR 검수 내용 저장 완료', result.items.length + '개 영역의 변경 내용을 한 번에 저장했습니다.')
    },
    onError: error => { reviewQuery.refetch(); notify('error', error.status === 409 ? '수정 내용 충돌' : 'OCR 검수 내용 저장 실패', error.message) },
  })

  const exclusionMutation = useMutation({
    mutationFn: element => setOcrElementExclusion(projectId, documentId, element.id, !element.is_excluded, element.version),
    onSuccess: updated => {
      queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: current.ocr_revision + 1, review_status: 'IN_PROGRESS', pages: current.pages.map(item => ({ ...item, elements: item.elements.map(element => element.id === updated.id ? updated : element) })) }) : current)
      queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true })
      notify('success', updated.is_excluded ? '본문 제외 예정' : '본문 포함 예정', '검수 완료 시 최종 문서 텍스트에 반영됩니다.')
    },
    onError: error => { reviewQuery.refetch(); notify('error', error.status === 409 ? '본문 포함 설정 충돌' : 'OCR 본문 포함 설정 실패', error.message) },
  })

  const completeMutation = useMutation({
    mutationFn: () => completeOcrReview(projectId, documentId),
    onSuccess: result => { setDrafts({}); setStructureDrafts({}); queryClient.setQueryData(reviewKey, result); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] }); queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true }); notify('success', 'OCR 검수 완료', '검수 결과가 최종 텍스트에 반영되었습니다.') },
    onError: error => notify('error', '검수 완료 처리 실패', error.message),
  })

  function completeReview() {
    if (!confirmDiscard('저장하지 않은 수정 내용이 있습니다. 저장하지 않고 검수를 완료할까요?')) return
    completeMutation.mutate()
  }

  if (projectQuery.isError) return <div className='center'><p>프로젝트에 접근할 수 없습니다.</p><button onClick={() => navigate('/projects')}>내 프로젝트로 이동</button></div>
  if (documentQuery.isPending || reviewQuery.isPending) return <LoadingState label='OCR 검수 데이터를 불러오는 중...'/>
  if (documentQuery.isError || reviewQuery.isError || !page) return <div className='ocr-review-error'><h1>OCR 검수 화면을 열 수 없습니다.</h1><p>문서가 없거나 검수할 OCR 페이지가 없습니다.</p><button onClick={() => navigate('/projects/' + projectId + '/documents/' + documentId)}>문서 상세로 돌아가기</button></div>

  const documentPageCount = documentQuery.data?.page_count ?? pages.length
  const selectedIndex = effectivePageElements.findIndex(element => element.id === effectiveSelectedId)
  const effectivePage = { ...page, elements: effectivePageElements }
  return <div className='ocr-review-page'>
    <AppHeader user={user} onLogout={onLogout} notify={notify} project={projectQuery.data}/>
    <header className='ocr-review-toolbar'>
      <div className='ocr-review-title'><button className='back-button' onClick={goBack}>← 문서로 돌아가기</button><h1>{documentQuery.data?.filename ?? 'OCR 검수'}</h1><p>문서 {page.page_number}/{documentPageCount}쪽 · OCR 대상 {pageIndex + 1}/{pages.length}쪽</p></div>
      <div className='ocr-review-toolbar-actions'><span className={'status-badge status-' + reviewStatus.tone} title={reviewStatus.description}>{reviewStatus.label}</span><button className='primary' disabled={!canEdit || completeMutation.isPending || updateMutation.isPending || exclusionMutation.isPending} onClick={completeReview}>{completeMutation.isPending ? '검수 완료 처리 중...' : 'OCR 검수 완료'}</button></div>
    </header>
    <section className='ocr-review-progress' aria-label='OCR 검수 진행 현황'><div><span>OCR 요소</span><strong>{totalElements}개</strong></div><div><span>수정 또는 제외 예정</span><strong>{changedElements}개</strong></div><div><span>현재 선택 영역</span><strong>{selectedIndex >= 0 ? String(selectedIndex + 1) + '/' + effectivePageElements.length : '선택된 항목 없음'}</strong></div><p className={hasUnsavedChanges ? 'has-unsaved' : ''}>{hasUnsavedChanges ? '저장하지 않은 변경 사항이 있습니다.' : '현재 선택 영역의 변경 사항은 저장된 상태입니다.'}</p></section>
    <main className='ocr-review-workspace ocr-review-layout'>
      <section className='ocr-canvas-panel'><div className='ocr-canvas-toolbar'><ConfidenceLegend/><PageNavigator pageIndex={pageIndex} pageCount={pages.length} onChange={changePage}/><div className='ocr-page-context'><strong>원본 문서 {page.page_number}쪽</strong><small>현재 확인 중인 OCR 원본 페이지</small></div></div><OcrCanvas page={effectivePage} selectedId={effectiveSelectedId} onSelect={element => selectElement(element, true)}/></section>
      <aside className='ocr-editor-panel'><div className='ocr-editor-heading'><div><h2>인식 텍스트</h2><p>텍스트 종류와 단락 경계를 확인한 뒤 변경 내용을 한 번에 저장합니다.</p></div><span>{effectivePageElements.length}개</span></div><ElementList elements={effectivePageElements} filter={elementFilter} lowConfidenceCount={lowConfidenceElements.length} onFilterChange={changeElementFilter} selectedId={effectiveSelectedId} onSelect={selectElement} draft={draft} onDraft={text => selected && setDrafts(current => ({ ...current, [selected.id]: text }))} onStructureChange={updateStructure} onApplyAutomaticParagraphs={applyAutomaticParagraphs} canEdit={canEdit} saving={updateMutation.isPending || completeMutation.isPending || exclusionMutation.isPending} excluding={exclusionMutation.isPending || updateMutation.isPending || completeMutation.isPending} unsavedCount={dirtyChanges.length} onSave={() => updateMutation.mutate(dirtyChanges)} onToggleExclusion={element => exclusionMutation.mutate(element)}/></aside>
    </main>
  </div>
}

function OcrCanvas({ page, selectedId, onSelect }) {
  const imageQuery = useQuery({ queryKey: ['ocr-page-image', page.id], queryFn: () => getOcrPageImage(page.image_url), staleTime: Infinity })
  if (imageQuery.isPending) return <LoadingState label='원본 이미지를 불러오는 중...'/>
  const paragraphGroups = paragraphGroupNumbers(page.elements)
  return <div className='ocr-canvas-scroll'><div className='ocr-canvas'><img src={imageQuery.data} alt={String(page.page_number) + '페이지 원본'}/>{page.elements.map(element => <button key={element.id} title={element.text} aria-label={'OCR 영역: ' + element.text} className={'ocr-box confidence-' + confidenceLevel(element.confidence) + ' paragraph-group-' + (paragraphGroups.get(element.id) % 6) + (selectedId === element.id ? ' selected' : '')} style={{ left: String(element.x * 100) + '%', top: String(element.y * 100) + '%', width: String(element.width * 100) + '%', height: String(element.height * 100) + '%' }} onClick={() => onSelect(element)}/>)}</div></div>
}

function PageNavigator({ pageIndex, pageCount, onChange }) {
  return <div className='page-navigator'><button disabled={pageIndex === 0} onClick={() => onChange(pageIndex - 1)}>← 이전</button><strong>OCR 대상 {pageIndex + 1}/{pageCount}</strong><button disabled={pageIndex + 1 >= pageCount} onClick={() => onChange(pageIndex + 1)}>다음 →</button></div>
}

function ConfidenceLegend() { return <div className='confidence-legend'><span className='high'>높음</span><span className='medium'>검토 권장</span><span className='low'>낮음</span><span className='selected-key'>선택 영역</span></div> }

function ElementList({ elements, filter, lowConfidenceCount, onFilterChange, selectedId, onSelect, draft, onDraft, onStructureChange, onApplyAutomaticParagraphs, canEdit, saving, excluding, unsavedCount, onSave, onToggleExclusion }) {
  const visibleElements = elements.map((element, index) => ({ element, index })).filter(({ element }) => filter === 'ALL' || confidenceLevel(element.confidence) === 'low')
  return <section className='ocr-element-list'><div className='ocr-element-list-title'><h3>현재 페이지 OCR 영역 <span>{elements.length}</span></h3><button type='button' disabled={!canEdit || saving} onClick={onApplyAutomaticParagraphs}>자동 단락 제안</button></div><div className='ocr-confidence-filter' role='group' aria-label='OCR 신뢰도 필터'><button type='button' className={filter === 'ALL' ? 'active' : ''} aria-pressed={filter === 'ALL'} onClick={() => onFilterChange('ALL')}>전체 <span>{elements.length}</span></button><button type='button' className={filter === 'LOW' ? 'active' : ''} aria-pressed={filter === 'LOW'} onClick={() => onFilterChange('LOW')}>낮은 신뢰도 <span>{lowConfidenceCount}</span></button></div>{visibleElements.length === 0 && <div className='ocr-filter-empty'><strong>낮은 신뢰도 영역이 없습니다.</strong><p>현재 페이지의 OCR 요소가 모두 기준 신뢰도 이상입니다.</p></div>}{visibleElements.map(({ element, index }) => <div className='ocr-element-with-boundary' key={element.id}><ParagraphBoundary element={element} index={index} canEdit={canEdit && !saving} onChange={value => onStructureChange(element, { is_paragraph_start: value })}/><article id={'ocr-element-' + element.id} className={(selectedId === element.id ? 'active' : '') + (element.is_excluded ? ' excluded' : '')}><button className='ocr-element-summary' onClick={() => onSelect(element)}><i className={'confidence-dot confidence-' + confidenceLevel(element.confidence)}/><span>{index + 1}. {element.text || '(빈 텍스트)'}</span><small>{elementTypeLabel(element.element_type)} · {element.is_excluded ? '제외 예정' : 'v' + element.version}</small></button>{selectedId === element.id && <div className='inline-ocr-editor'><ConfidenceSummary confidence={element.confidence}/><label className='ocr-element-type'>요소 종류<select value={element.element_type} disabled={!canEdit || saving} onChange={event => onStructureChange(element, { element_type: event.target.value })}>{OCR_ELEMENT_TYPES.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label><label>선택 영역 텍스트<textarea value={draft} readOnly={!canEdit} onChange={event => onDraft(event.target.value)}/></label><div className='original-value'><span>최초 인식 원문</span><p>{element.original_text}</p></div><div className='ocr-edit-actions'><button className={element.is_excluded ? 'include-ocr' : 'exclude-ocr'} disabled={!canEdit || excluding} onClick={() => onToggleExclusion(element)}>{element.is_excluded ? '본문에 다시 포함' : '본문에서 제외'}</button></div></div>}</article></div>)}<div className='ocr-sticky-save' role='status'><span className={unsavedCount ? 'has-unsaved' : ''}>{unsavedCount ? '미저장 변경 ' + unsavedCount + '개' : '변경 사항 저장됨'}</span><button className='primary' disabled={!canEdit || !unsavedCount || saving} onClick={onSave}>{saving ? '저장 중...' : '변경 내용 일괄 저장'}</button></div></section>
}

function ParagraphBoundary({ element, index, canEdit, onChange }) {
  if (index === 0) return <div className='paragraph-boundary fixed'><span>페이지 시작</span></div>
  if (isTableElement(element)) return <div className='paragraph-boundary table'><span>표 내부</span></div>
  if (element.element_type === 'HEADING') return <div className='paragraph-boundary fixed'><span>제목 단락</span></div>
  return <div className={'paragraph-boundary' + (element.is_paragraph_start ? ' active' : '')}><button type='button' disabled={!canEdit} onClick={() => onChange(!element.is_paragraph_start)}>{element.is_paragraph_start ? '─ 단락 합치기' : '+ 단락 나누기'}</button></div>
}

function ConfidenceSummary({ confidence }) { const level = confidenceLevel(confidence); return <div className={'confidence-summary confidence-' + level}><strong>인식 신뢰도</strong><span>{confidence == null ? '정보 없음' : String(Math.round(confidence * 100)) + '%'}</span></div> }
function confidenceLevel(value) { if (value == null || value < .65) return 'low'; if (value < .85) return 'medium'; return 'high' }

const OCR_ELEMENT_TYPES = [
  { value: 'TEXT_LINE', label: '본문 줄' },
  { value: 'HEADING', label: '제목·조항 제목' },
  { value: 'TABLE_ROW', label: '표 행' },
  { value: 'TABLE_HEADER', label: '표 머리행' },
  { value: 'HEADER_FOOTER', label: '머리글·바닥글' },
]

function elementTypeLabel(value) { return OCR_ELEMENT_TYPES.find(type => type.value === value)?.label ?? value }
function isTableElement(element) { return element.element_type === 'TABLE_ROW' || element.element_type === 'TABLE_HEADER' }

function buildBatchChange(element, textDraft, structureDraft) {
  const change = { id: element.id, version: element.version }
  if (textDraft !== undefined && textDraft !== element.text) change.text = textDraft
  if (structureDraft?.is_paragraph_start !== undefined && structureDraft.is_paragraph_start !== element.is_paragraph_start) change.is_paragraph_start = structureDraft.is_paragraph_start
  if (structureDraft?.element_type !== undefined && structureDraft.element_type !== element.element_type) change.element_type = structureDraft.element_type
  return Object.keys(change).length > 2 ? change : null
}

function suggestParagraphStarts(elements) {
  const suggestions = new Map()
  elements.forEach((element, index) => {
    if (index === 0 || isTableElement(element)) return
    if (element.element_type === 'HEADING') { suggestions.set(element.id, true); return }
    const previous = elements[index - 1]
    const indentation = element.x - previous.x
    const verticalGap = element.y - (previous.y + previous.height)
    const referenceHeight = Math.max(previous.height, element.height, 0.01)
    suggestions.set(element.id, indentation >= 0.025 || verticalGap >= referenceHeight * 0.8)
  })
  return suggestions
}

function paragraphGroupNumbers(elements) {
  const groups = new Map()
  let group = 0
  elements.forEach((element, index) => {
    const previous = elements[index - 1]
    const beginsTable = isTableElement(element) && (!previous || previous.table_id !== element.table_id)
    if (index > 0 && (element.is_paragraph_start || element.element_type === 'HEADING' || beginsTable)) group += 1
    groups.set(element.id, group)
  })
  return groups
}

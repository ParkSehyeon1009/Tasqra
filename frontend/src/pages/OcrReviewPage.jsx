import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { useBlocker, useNavigate, useParams } from 'react-router-dom'
import { completeOcrReview, createOcrElement, getDocument, getOcrPageImage, getOcrReview, mergeOcrElements, reprocessOcrElement, setOcrElementDeletion, setOcrElementExclusion, undoOcrElementMerge, updateOcrElementsBatch } from '../api/document'
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
  const [geometryDrafts, setGeometryDrafts] = useState({})
  const [reOcrDrafts, setReOcrDrafts] = useState({})
  const [reOcrResult, setReOcrResult] = useState(null)
  const [batchReOcrResults, setBatchReOcrResults] = useState(null)
  const [mergeMode, setMergeMode] = useState(false)
  const [mergeSelection, setMergeSelection] = useState([])
  const [mergePreview, setMergePreview] = useState(null)
  const [lastMerge, setLastMerge] = useState(null)
  const [elementFilter, setElementFilter] = useState('ALL')
  const [createMode, setCreateMode] = useState(false)
  const allowNavigationRef = useRef(false)
  const projectQuery = useQuery({ queryKey: ['project-access', projectId], queryFn: () => getProject(projectId), retry: false })
  const documentQuery = useQuery({ queryKey: ['projects', projectId, 'documents', documentId], queryFn: () => getDocument(projectId, documentId) })
  const reviewKey = ['projects', projectId, 'documents', documentId, 'ocr-review']
  const reviewQuery = useQuery({ queryKey: reviewKey, queryFn: () => getOcrReview(projectId, documentId), refetchOnMount: 'always' })
  const review = reviewQuery.data
  const availableLastMerge = lastMerge ?? (review?.latest_merge_operation_id ? { operationId: review.latest_merge_operation_id, pageId: review.latest_merge_page_id } : null)
  const pages = review?.pages ?? []
  const page = pages[pageIndex]
  const effectiveSelectedId = selectedId ?? page?.elements[0]?.id ?? null
  const selectedSource = useMemo(() => page?.elements.find(item => item.id === effectiveSelectedId) ?? null, [page, effectiveSelectedId])
  const selected = selectedSource ? { ...selectedSource, ...structureDrafts[selectedSource.id] } : null
  const draft = selected ? (drafts[selected.id] ?? selected.text) : ''
  const effectivePageElements = useMemo(() => page?.elements.map(element => ({ ...element, ...structureDrafts[element.id], ...geometryDrafts[element.id] })) ?? [], [page, structureDrafts, geometryDrafts])
  const lowConfidenceElements = useMemo(() => effectivePageElements.filter(element => !element.is_deleted && confidenceLevel(element.confidence) === 'low'), [effectivePageElements])
  const undoableMergeBySurvivor = useMemo(() => new Map((review?.undoable_merges ?? []).map(operation => [operation.survivor_id, operation])), [review?.undoable_merges])
  const mergeableParagraphGroups = useMemo(() => paragraphMergeGroups(effectivePageElements), [effectivePageElements])
  const selectedMergeOperation = undoableMergeBySurvivor.get(effectiveSelectedId)
  const canEdit = projectQuery.data?.role !== 'VIEWER'
  const dirtyChanges = pages.flatMap(item => item.elements.map(element => buildBatchChange(element, drafts[element.id], structureDrafts[element.id], geometryDrafts[element.id], reOcrDrafts[element.id])).filter(Boolean))
  const hasUnsavedChanges = dirtyChanges.length > 0
  const totalElements = pages.reduce((count, item) => count + item.elements.filter(element => !element.is_deleted).length, 0)
  const changedElements = pages.reduce((count, item) => count + item.elements.filter(element => !element.is_deleted && (element.version > 1 || element.is_excluded)).length, 0)
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

  function updateGeometry(element, geometry) {
    setGeometryDrafts(current => ({ ...current, [element.id]: geometry }))
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

  function mergeSuggestedParagraphs() {
    if (hasUnsavedChanges) {
      notify('error', '단락 병합 전 저장 필요', '자동 단락 제안이나 다른 변경 내용을 먼저 저장해 주세요.')
      return
    }
    if (!mergeableParagraphGroups.length) return
    if (window.confirm(`${mergeableParagraphGroups.length}개 단락의 박스와 텍스트를 합칠까요? 병합된 박스는 각각 다시 나눌 수 있습니다.`)) paragraphMergeMutation.mutate(mergeableParagraphGroups)
  }

  const updateMutation = useMutation({
    mutationFn: changes => updateOcrElementsBatch(projectId, documentId, changes),
    onSuccess: result => {
      const updatedById = new Map(result.items.map(element => [element.id, element]))
      queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: result.ocr_revision, review_status: 'IN_PROGRESS', pages: current.pages.map(item => ({ ...item, elements: item.elements.map(element => updatedById.get(element.id) ?? element) })) }) : current)
      setDrafts({})
      setStructureDrafts({})
      setGeometryDrafts({})
      setReOcrDrafts({})
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

  const createMutation = useMutation({
    mutationFn: geometry => createOcrElement(projectId, documentId, { page_id: page.id, text: '새 OCR 영역', ...geometry }),
    onSuccess: created => {
      queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: current.ocr_revision + 1, review_status: 'IN_PROGRESS', pages: current.pages.map(item => item.id === page.id ? { ...item, elements: [...item.elements, created] } : item) }) : current)
      setCreateMode(false)
      setSelectedId(created.id)
      notify('success', 'OCR 박스 추가', '새 영역의 위치와 텍스트를 조정한 뒤 저장해 주세요.')
    },
    onError: error => notify('error', 'OCR 박스 추가 실패', error.message),
  })

  const deletionMutation = useMutation({
    mutationFn: element => setOcrElementDeletion(projectId, documentId, element.id, !element.is_deleted, element.version),
    onSuccess: updated => {
      queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: current.ocr_revision + 1, review_status: 'IN_PROGRESS', pages: current.pages.map(item => ({ ...item, elements: item.elements.map(element => element.id === updated.id ? updated : element) })) }) : current)
      setDrafts(current => { const next = { ...current }; delete next[updated.id]; return next })
      setStructureDrafts(current => { const next = { ...current }; delete next[updated.id]; return next })
      setGeometryDrafts(current => { const next = { ...current }; delete next[updated.id]; return next })
      notify('success', updated.is_deleted ? 'OCR 박스 삭제' : 'OCR 박스 복원', updated.is_deleted ? '삭제된 박스는 이 목록에서 다시 복원할 수 있습니다.' : '박스가 본문과 원본 화면에 다시 표시됩니다.')
    },
    onError: error => { reviewQuery.refetch(); notify('error', 'OCR 박스 상태 변경 실패', error.message) },
  })

  const reOcrMutation = useMutation({
    mutationFn: element => reprocessOcrElement(projectId, documentId, element),
    onSuccess: result => setReOcrResult(result),
    onError: error => notify('error', '선택 영역 재OCR 실패', error.message),
  })

  const batchReOcrMutation = useMutation({
    mutationFn: async elements => {
      const results = []
      for (const element of elements) {
        try {
          results.push({ status: 'SUCCESS', element, result: await reprocessOcrElement(projectId, documentId, element) })
        } catch (error) {
          results.push({ status: 'FAILED', element, error: error.message || '재OCR에 실패했습니다.' })
        }
      }
      return results
    },
    onSuccess: results => setBatchReOcrResults(results),
  })

  const mergeMutation = useMutation({
    mutationFn: preview => mergeOcrElements(projectId, documentId, preview.elements, preview.joinWithSpace),
    onSuccess: result => {
      queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: result.ocr_revision, review_status: 'IN_PROGRESS', undoable_merges: [{ operation_id: result.merge_operation_id, survivor_id: result.merged.id, page_id: page.id }, ...(current.undoable_merges ?? [])], pages: current.pages.map(item => item.id === page.id ? { ...item, elements: [...item.elements.filter(element => !result.deleted_ids.includes(element.id)), result.merged].sort((a, b) => a.reading_order - b.reading_order) } : item) }) : current)
      setMergeMode(false)
      setMergeSelection([])
      setMergePreview(null)
      setLastMerge({ operationId: result.merge_operation_id, pageId: page.id })
      setSelectedId(result.merged.id)
      notify('success', 'OCR 박스 병합 완료', `${result.deleted_ids.length}개 영역을 하나로 병합했습니다.`)
    },
    onError: error => notify('error', 'OCR 박스 병합 실패', error.message),
  })

  const undoMergeMutation = useMutation({
    mutationFn: operation => undoOcrElementMerge(projectId, documentId, operation.operationId),
    onSuccess: (result, operation) => {
      const restoredIds = new Set(result.restored.map(element => element.id))
      queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: result.ocr_revision, review_status: 'IN_PROGRESS', latest_merge_operation_id: null, latest_merge_page_id: null, undoable_merges: (current.undoable_merges ?? []).filter(item => item.operation_id !== operation.operationId), pages: current.pages.map(item => item.id === operation.pageId ? { ...item, elements: [...item.elements.filter(element => !restoredIds.has(element.id) && !result.deleted_ids.includes(element.id)), ...result.restored].sort((a, b) => a.reading_order - b.reading_order) } : item) }) : current)
      setLastMerge(null)
      setSelectedId(result.restored[0]?.id ?? null)
      notify('success', '박스 병합 되돌리기 완료', '병합 전 박스와 텍스트를 복원했습니다.')
    },
    onError: error => { setLastMerge(null); reviewQuery.refetch(); notify('error', '병합 되돌리기 실패', error.message) },
  })

  const paragraphMergeMutation = useMutation({
    mutationFn: async groups => {
      const results = []
      for (const group of groups) {
        try { results.push({ status: 'SUCCESS', result: await mergeOcrElements(projectId, documentId, group, true) }) }
        catch (error) { results.push({ status: 'FAILED', error }) }
      }
      return results
    },
    onSuccess: results => {
      const successes = results.filter(item => item.status === 'SUCCESS').map(item => item.result)
      queryClient.setQueryData(reviewKey, current => {
        if (!current) return current
        let elements = current.pages.find(item => item.id === page.id)?.elements ?? []
        successes.forEach(result => { elements = [...elements.filter(element => !result.deleted_ids.includes(element.id)), result.merged].sort((a, b) => a.reading_order - b.reading_order) })
        return { ...current, ocr_revision: successes.at(-1)?.ocr_revision ?? current.ocr_revision, review_status: 'IN_PROGRESS', undoable_merges: [...successes.map(result => ({ operation_id: result.merge_operation_id, survivor_id: result.merged.id, page_id: page.id })), ...(current.undoable_merges ?? [])], pages: current.pages.map(item => item.id === page.id ? { ...item, elements } : item) }
      })
      const failures = results.length - successes.length
      setLastMerge(successes.length ? { operationId: successes.at(-1).merge_operation_id, pageId: page.id } : null)
      setSelectedId(successes[0]?.merged.id ?? null)
      notify(failures ? 'error' : 'success', '단락별 박스 병합 완료', `${successes.length}개 단락 병합 성공${failures ? ` · ${failures}개 실패` : ''}`)
    },
  })

  function toggleMergeSelection(element) {
    setMergeSelection(current => current.includes(element.id) ? current.filter(id => id !== element.id) : [...current, element.id])
  }

  function mergeSelectedElements() {
    if (hasUnsavedChanges) {
      notify('error', '박스 병합 전 저장 필요', '텍스트나 좌표 변경 내용을 먼저 저장한 뒤 병합해 주세요.')
      return
    }
    const selectedElements = effectivePageElements.filter(element => mergeSelection.includes(element.id))
    const texts = selectedElements.slice().sort((a, b) => a.reading_order - b.reading_order).map(element => element.text).filter(Boolean)
    setMergePreview({ elements: selectedElements, texts, joinWithSpace: true, text: texts.join(' ') })
  }

  function applyReOcrResult() {
    if (!reOcrResult) return
    setDrafts(current => ({ ...current, [reOcrResult.element_id]: reOcrResult.recognized_text }))
    setReOcrDrafts(current => ({ ...current, [reOcrResult.element_id]: { confidence: reOcrResult.confidence } }))
    setReOcrResult(null)
  }

  function applyBatchReOcrResults() {
    const successes = (batchReOcrResults ?? []).filter(item => item.status === 'SUCCESS')
    setDrafts(current => ({ ...current, ...Object.fromEntries(successes.map(item => [item.element.id, item.result.recognized_text])) }))
    setReOcrDrafts(current => ({ ...current, ...Object.fromEntries(successes.map(item => [item.element.id, { confidence: item.result.confidence }])) }))
    setBatchReOcrResults(null)
    notify('success', '일괄 재OCR 결과 적용', `${successes.length}개 영역을 변경 초안에 반영했습니다. 하단 저장 버튼을 눌러 확정해 주세요.`)
  }

  const completeMutation = useMutation({
    mutationFn: () => completeOcrReview(projectId, documentId),
    onSuccess: result => { setDrafts({}); setStructureDrafts({}); setGeometryDrafts({}); setReOcrDrafts({}); queryClient.setQueryData(reviewKey, result); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] }); queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true }); notify('success', 'OCR 검수 완료', '검수 결과가 최종 텍스트에 반영되었습니다.') },
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
    {canEdit && <section className='ocr-paragraph-merge-actions'><div><strong>단락 박스 정리</strong><span>자동 단락 제안과 직접 조정한 경계를 기준으로 박스와 텍스트를 합칩니다.</span></div><button type='button' disabled={!mergeableParagraphGroups.length || paragraphMergeMutation.isPending} onClick={mergeSuggestedParagraphs}>{paragraphMergeMutation.isPending ? '단락 병합 중...' : `단락별 박스 병합 (${mergeableParagraphGroups.length})`}</button>{selectedMergeOperation && <button type='button' className='restore' disabled={undoMergeMutation.isPending} onClick={() => undoMergeMutation.mutate({ operationId: selectedMergeOperation.operation_id, pageId: selectedMergeOperation.page_id })}>{undoMergeMutation.isPending ? '나누는 중...' : '선택 박스 원래대로 나누기'}</button>}</section>}
    <main className='ocr-review-workspace ocr-review-layout'>
      <section className='ocr-canvas-panel'><div className='ocr-canvas-toolbar'><ConfidenceLegend/><PageNavigator pageIndex={pageIndex} pageCount={pages.length} onChange={changePage}/><div className='ocr-page-context'><strong>원본 문서 {page.page_number}쪽</strong><small>{mergeMode ? '합칠 인접 박스를 원본 화면에서 차례로 선택하세요.' : createMode ? '원본에서 원하는 영역을 대각선으로 드래그하세요.' : '박스를 끌어서 이동하고 우하단 손잡이로 크기를 조정합니다.'}</small></div></div><OcrCanvas page={effectivePage} selectedId={effectiveSelectedId} canEdit={canEdit} createMode={createMode} mergeMode={mergeMode} mergeSelection={mergeSelection} onCreate={geometry => createMutation.mutate(geometry)} onSelect={element => mergeMode ? toggleMergeSelection(element) : selectElement(element, true)} onGeometryChange={updateGeometry}/></section>
      <aside className='ocr-editor-panel'><div className='ocr-editor-heading'><div><h2>인식 텍스트</h2><p>텍스트 종류와 단락 경계를 확인한 뒤 변경 내용을 한 번에 저장합니다.</p></div><div className='ocr-editor-heading-actions'><span>{effectivePageElements.filter(element => !element.is_deleted).length}개</span>{canEdit && <button type='button' className={createMode ? 'active' : ''} disabled={createMutation.isPending} onClick={() => setCreateMode(current => !current)}>{createMode ? '추가 취소' : '+ 박스 추가'}</button>}</div></div>{canEdit && <div className='ocr-batch-reocr'><span>일괄 재OCR</span><button type='button' disabled={!lowConfidenceElements.length || batchReOcrMutation.isPending} onClick={() => batchReOcrMutation.mutate(lowConfidenceElements)}>낮은 신뢰도 {lowConfidenceElements.length}개</button><button type='button' disabled={!effectivePageElements.length || batchReOcrMutation.isPending} onClick={() => batchReOcrMutation.mutate(effectivePageElements.filter(element => !element.is_deleted))}>현재 페이지 전체</button>{batchReOcrMutation.isPending && <small>선택 영역을 순서대로 처리하고 있습니다...</small>}</div>}{canEdit && <div className='ocr-merge-toolbar'><button type='button' className={mergeMode ? 'active' : ''} onClick={() => { setMergeMode(current => !current); setMergeSelection([]) }}>{mergeMode ? '병합 선택 취소' : '박스 병합'}</button>{mergeMode && <><span>{mergeSelection.length}개 선택</span><button type='button' className='primary' disabled={mergeSelection.length < 2 || mergeMutation.isPending} onClick={mergeSelectedElements}>선택 박스 병합</button></>}{availableLastMerge && <button type='button' disabled={undoMergeMutation.isPending} onClick={() => undoMergeMutation.mutate(availableLastMerge)}>{undoMergeMutation.isPending ? '되돌리는 중...' : '최근 병합 되돌리기'}</button>}</div>}<ElementList elements={effectivePageElements} filter={elementFilter} lowConfidenceCount={lowConfidenceElements.length} onFilterChange={changeElementFilter} selectedId={effectiveSelectedId} onSelect={selectElement} draft={draft} onDraft={text => selected && setDrafts(current => ({ ...current, [selected.id]: text }))} onStructureChange={updateStructure} onApplyAutomaticParagraphs={applyAutomaticParagraphs} canEdit={canEdit} saving={updateMutation.isPending || completeMutation.isPending || exclusionMutation.isPending || deletionMutation.isPending || reOcrMutation.isPending || batchReOcrMutation.isPending || mergeMutation.isPending || undoMergeMutation.isPending} excluding={exclusionMutation.isPending || updateMutation.isPending || completeMutation.isPending || deletionMutation.isPending} unsavedCount={dirtyChanges.length} onSave={() => updateMutation.mutate(dirtyChanges)} onToggleExclusion={element => exclusionMutation.mutate(element)} onToggleDeletion={element => deletionMutation.mutate(element)} onReOcr={element => reOcrMutation.mutate(element)} mergeMode={mergeMode} mergeSelection={mergeSelection} onToggleMerge={toggleMergeSelection}/></aside>
    </main>
    {reOcrResult && <div className='reocr-dialog-backdrop' role='presentation' onMouseDown={() => setReOcrResult(null)}><section className='reocr-dialog' role='dialog' aria-modal='true' aria-labelledby='reocr-title' onMouseDown={event => event.stopPropagation()}><h2 id='reocr-title'>재OCR 결과 비교</h2><p>새 인식 결과를 확인한 뒤 적용하세요. 적용 후에도 하단 저장 버튼을 눌러야 확정됩니다.</p><div className='reocr-comparison'><div><span>현재 텍스트</span><pre>{reOcrResult.original_text}</pre></div><div><span>새 인식 결과 {reOcrResult.confidence == null ? '' : `· ${Math.round(reOcrResult.confidence * 100)}%`}</span><pre>{reOcrResult.recognized_text}</pre></div></div><div className='reocr-dialog-actions'><button onClick={() => setReOcrResult(null)}>취소</button><button className='primary' onClick={applyReOcrResult}>새 결과 적용</button></div></section></div>}
    {batchReOcrResults && <div className='reocr-dialog-backdrop' role='presentation' onMouseDown={() => setBatchReOcrResults(null)}><section className='reocr-dialog batch-reocr-dialog' role='dialog' aria-modal='true' aria-labelledby='batch-reocr-title' onMouseDown={event => event.stopPropagation()}><h2 id='batch-reocr-title'>일괄 재OCR 결과</h2><p>성공한 결과를 검토하고 한꺼번에 변경 초안으로 적용할 수 있습니다.</p><ul>{batchReOcrResults.map(item => <li key={item.element.id} className={item.status === 'SUCCESS' ? 'success' : 'failed'}><div><strong>{item.element.text || '(빈 텍스트)'}</strong><span>{item.status === 'SUCCESS' ? '→ ' + item.result.recognized_text : item.error}</span></div><small>{item.status === 'SUCCESS' ? (item.result.confidence == null ? '신뢰도 정보 없음' : `신뢰도 ${Math.round(item.result.confidence * 100)}%`) : '실패'}</small></li>)}</ul><div className='reocr-dialog-actions'><button onClick={() => setBatchReOcrResults(null)}>취소</button><button className='primary' disabled={!batchReOcrResults.some(item => item.status === 'SUCCESS')} onClick={applyBatchReOcrResults}>성공 결과 전체 적용</button></div></section></div>}
    {mergePreview && <div className='reocr-dialog-backdrop' role='presentation' onMouseDown={() => setMergePreview(null)}><section className='reocr-dialog merge-preview-dialog' role='dialog' aria-modal='true' aria-labelledby='merge-preview-title' onMouseDown={event => event.stopPropagation()}><h2 id='merge-preview-title'>박스 병합 미리보기</h2><p>{mergePreview.elements.length}개 박스가 아래 텍스트로 합쳐집니다.</p><label className='merge-linebreak-option'><input type='checkbox' checked={mergePreview.joinWithSpace} onChange={event => setMergePreview(current => ({ ...current, joinWithSpace: event.target.checked, text: current.texts.join(event.target.checked ? ' ' : '\n') }))}/>박스 사이 줄바꿈 없이 연결</label><pre>{mergePreview.text}</pre><div className='reocr-dialog-actions'><button onClick={() => setMergePreview(null)}>취소</button><button className='primary' disabled={mergeMutation.isPending} onClick={() => mergeMutation.mutate(mergePreview)}>{mergeMutation.isPending ? '병합 중...' : '이대로 병합'}</button></div></section></div>}
  </div>
}

function OcrCanvas({ page, selectedId, canEdit, createMode, mergeMode, mergeSelection, onCreate, onSelect, onGeometryChange }) {
  const imageQuery = useQuery({ queryKey: ['ocr-page-image', page.id], queryFn: () => getOcrPageImage(page.image_url), staleTime: Infinity })
  const [creation, setCreation] = useState(null)
  if (imageQuery.isPending) return <LoadingState label='원본 이미지를 불러오는 중...'/>
  const paragraphGroups = paragraphGroupNumbers(page.elements)

  function beginCreation(event) {
    if (!createMode || event.target.tagName !== 'IMG') return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    const bounds = event.currentTarget.getBoundingClientRect()
    const x = clamp((event.clientX - bounds.left) / bounds.width, 0, 1)
    const y = clamp((event.clientY - bounds.top) / bounds.height, 0, 1)
    setCreation({ pointerId: event.pointerId, bounds, startX: x, startY: y, x, y, width: 0, height: 0 })
  }

  function moveCreation(event) {
    if (!creation || creation.pointerId !== event.pointerId) return
    const currentX = clamp((event.clientX - creation.bounds.left) / creation.bounds.width, 0, 1)
    const currentY = clamp((event.clientY - creation.bounds.top) / creation.bounds.height, 0, 1)
    setCreation(current => ({ ...current, x: Math.min(current.startX, currentX), y: Math.min(current.startY, currentY), width: Math.abs(currentX - current.startX), height: Math.abs(currentY - current.startY) }))
  }

  function endCreation(event) {
    if (!creation || creation.pointerId !== event.pointerId) return
    const currentX = clamp((event.clientX - creation.bounds.left) / creation.bounds.width, 0, 1)
    const currentY = clamp((event.clientY - creation.bounds.top) / creation.bounds.height, 0, 1)
    const geometry = { x: Math.min(creation.startX, currentX), y: Math.min(creation.startY, currentY), width: Math.abs(currentX - creation.startX), height: Math.abs(currentY - creation.startY) }
    if (geometry.width >= .005 && geometry.height >= .005) onCreate(geometry)
    setCreation(null)
  }

  return <div className='ocr-canvas-scroll'><div className={'ocr-canvas' + (createMode ? ' is-creating' : '') + (mergeMode ? ' is-merging' : '')} onPointerDown={beginCreation} onPointerMove={moveCreation} onPointerUp={endCreation} onPointerCancel={() => setCreation(null)}><img src={imageQuery.data} draggable='false' alt={String(page.page_number) + '페이지 원본'}/>{page.elements.filter(element => !element.is_deleted).map(element => <EditableOcrBox key={element.id} element={element} group={paragraphGroups.get(element.id) % 6} selected={selectedId === element.id} mergeSelected={mergeSelection.includes(element.id)} canEdit={canEdit && !createMode && !mergeMode} onSelect={onSelect} onGeometryChange={onGeometryChange}/>)}{creation && <span className='ocr-creation-preview' style={{ left: String(creation.x * 100) + '%', top: String(creation.y * 100) + '%', width: String(creation.width * 100) + '%', height: String(creation.height * 100) + '%' }}/>}</div></div>
}

function EditableOcrBox({ element, group, selected, mergeSelected, canEdit, onSelect, onGeometryChange }) {
  const [interaction, setInteraction] = useState(null)

  function beginInteraction(event) {
    if (!canEdit) return
    onSelect(element)
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    const canvas = event.currentTarget.parentElement.getBoundingClientRect()
    setInteraction({ mode: event.target.dataset.resize ? 'resize' : 'move', pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, canvasWidth: canvas.width, canvasHeight: canvas.height, original: { x: element.x, y: element.y, width: element.width, height: element.height } })
  }

  function moveInteraction(event) {
    if (!interaction || interaction.pointerId !== event.pointerId) return
    const dx = (event.clientX - interaction.startX) / interaction.canvasWidth
    const dy = (event.clientY - interaction.startY) / interaction.canvasHeight
    const original = interaction.original
    onGeometryChange(element, interaction.mode === 'move'
      ? { x: clamp(original.x + dx, 0, 1 - original.width), y: clamp(original.y + dy, 0, 1 - original.height), width: original.width, height: original.height }
      : { x: original.x, y: original.y, width: clamp(original.width + dx, .005, 1 - original.x), height: clamp(original.height + dy, .005, 1 - original.y) })
  }

  function endInteraction(event) {
    if (!interaction || interaction.pointerId !== event.pointerId) return
    setInteraction(null)
  }

  return <button title={element.text} aria-label={'OCR 영역: ' + element.text} className={'ocr-box confidence-' + confidenceLevel(element.confidence) + ' paragraph-group-' + group + (selected ? ' selected' : '') + (mergeSelected ? ' merge-selected' : '') + (interaction ? ' is-adjusting' : '')} style={{ left: String(element.x * 100) + '%', top: String(element.y * 100) + '%', width: String(element.width * 100) + '%', height: String(element.height * 100) + '%' }} onClick={() => onSelect(element)} onPointerDown={beginInteraction} onPointerMove={moveInteraction} onPointerUp={endInteraction} onPointerCancel={endInteraction}>{selected && canEdit && <span className='ocr-resize-handle' data-resize='true' aria-hidden='true'/>}</button>
}

function PageNavigator({ pageIndex, pageCount, onChange }) {
  return <div className='page-navigator'><button disabled={pageIndex === 0} onClick={() => onChange(pageIndex - 1)}>← 이전</button><strong>OCR 대상 {pageIndex + 1}/{pageCount}</strong><button disabled={pageIndex + 1 >= pageCount} onClick={() => onChange(pageIndex + 1)}>다음 →</button></div>
}

function ConfidenceLegend() { return <div className='confidence-legend'><span className='high'>높음</span><span className='medium'>검토 권장</span><span className='low'>낮음</span><span className='selected-key'>선택 영역</span></div> }

function ElementList({ elements, filter, lowConfidenceCount, onFilterChange, selectedId, onSelect, draft, onDraft, onStructureChange, onApplyAutomaticParagraphs, canEdit, saving, excluding, unsavedCount, onSave, onToggleExclusion, onToggleDeletion, onReOcr }) {
  const visibleElements = elements.map((element, index) => ({ element, index })).filter(({ element }) => element.is_deleted || filter === 'ALL' || confidenceLevel(element.confidence) === 'low')
  return <section className='ocr-element-list'><div className='ocr-element-list-title'><h3>현재 페이지 OCR 영역 <span>{elements.length}</span></h3><button type='button' disabled={!canEdit || saving} onClick={onApplyAutomaticParagraphs}>자동 단락 제안</button></div><div className='ocr-confidence-filter' role='group' aria-label='OCR 신뢰도 필터'><button type='button' className={filter === 'ALL' ? 'active' : ''} aria-pressed={filter === 'ALL'} onClick={() => onFilterChange('ALL')}>전체 <span>{elements.length}</span></button><button type='button' className={filter === 'LOW' ? 'active' : ''} aria-pressed={filter === 'LOW'} onClick={() => onFilterChange('LOW')}>낮은 신뢰도 <span>{lowConfidenceCount}</span></button></div>{visibleElements.length === 0 && <div className='ocr-filter-empty'><strong>낮은 신뢰도 영역이 없습니다.</strong><p>현재 페이지의 OCR 요소가 모두 기준 신뢰도 이상입니다.</p></div>}{visibleElements.map(({ element, index }) => <div className={'ocr-element-with-boundary' + (element.is_deleted ? ' is-deleted' : '')} key={element.id}>{!element.is_deleted && <ParagraphBoundary element={element} index={index} canEdit={canEdit && !saving} onChange={value => onStructureChange(element, { is_paragraph_start: value })}/>}<article id={'ocr-element-' + element.id} className={(selectedId === element.id ? 'active' : '') + (element.is_excluded ? ' excluded' : '')}><button className='ocr-element-summary' onClick={() => onSelect(element)}><i className={'confidence-dot confidence-' + confidenceLevel(element.confidence)}/><span>{index + 1}. {element.text || '(빈 텍스트)'}</span><small>{element.is_deleted ? '삭제됨 · 복원 가능' : elementTypeLabel(element.element_type) + ' · ' + (element.is_excluded ? '제외 예정' : 'v' + element.version)}</small></button>{selectedId === element.id && <div className='inline-ocr-editor'>{!element.is_deleted && <><ConfidenceSummary confidence={element.confidence}/><label className='ocr-element-type'>요소 종류<select value={element.element_type} disabled={!canEdit || saving} onChange={event => onStructureChange(element, { element_type: event.target.value })}>{OCR_ELEMENT_TYPES.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label><label>선택 영역 텍스트<textarea value={draft} readOnly={!canEdit} onChange={event => onDraft(event.target.value)}/></label><div className='original-value'><span>최초 인식 원문</span><p>{element.original_text}</p></div></>}<div className='ocr-edit-actions'>{!element.is_deleted && <button className='reocr-button' disabled={!canEdit || saving} onClick={() => onReOcr(element)}>선택 영역 재OCR</button>}{!element.is_deleted && <button className={element.is_excluded ? 'include-ocr' : 'exclude-ocr'} disabled={!canEdit || excluding} onClick={() => onToggleExclusion(element)}>{element.is_excluded ? '본문에 다시 포함' : '본문에서 제외'}</button>}<button className={element.is_deleted ? 'restore-ocr' : 'delete-ocr'} disabled={!canEdit || saving} onClick={() => onToggleDeletion(element)}>{element.is_deleted ? '삭제한 박스 복원' : '박스 삭제'}</button></div></div>}</article></div>)}<div className='ocr-sticky-save' role='status'><span className={unsavedCount ? 'has-unsaved' : ''}>{unsavedCount ? '미저장 변경 ' + unsavedCount + '개' : '변경 사항 저장됨'}</span><button className='primary' disabled={!canEdit || !unsavedCount || saving} onClick={onSave}>{saving ? '저장 중...' : '변경 내용 일괄 저장'}</button></div></section>
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

function buildBatchChange(element, textDraft, structureDraft, geometryDraft, reOcrDraft) {
  const change = { id: element.id, version: element.version }
  if (textDraft !== undefined && textDraft !== element.text) change.text = textDraft
  if (structureDraft?.is_paragraph_start !== undefined && structureDraft.is_paragraph_start !== element.is_paragraph_start) change.is_paragraph_start = structureDraft.is_paragraph_start
  if (structureDraft?.element_type !== undefined && structureDraft.element_type !== element.element_type) change.element_type = structureDraft.element_type
  for (const field of ['x', 'y', 'width', 'height']) {
    if (geometryDraft?.[field] !== undefined && geometryDraft[field] !== element[field]) change[field] = geometryDraft[field]
  }
  if (reOcrDraft) { change.re_ocr_applied = true; change.re_ocr_confidence = reOcrDraft.confidence }
  return Object.keys(change).length > 2 ? change : null
}

function clamp(value, minimum, maximum) { return Math.min(Math.max(value, minimum), maximum) }

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

function paragraphMergeGroups(elements) {
  const groups = []
  let current = []
  const flush = () => {
    if (current.length > 1) groups.push(current)
    current = []
  }
  elements.slice().sort((a, b) => a.reading_order - b.reading_order).forEach(element => {
    if (element.is_deleted || element.is_excluded || isTableElement(element) || element.element_type === 'HEADING') {
      flush()
      return
    }
    if (element.is_paragraph_start) flush()
    current.push(element)
  })
  flush()
  return groups
}

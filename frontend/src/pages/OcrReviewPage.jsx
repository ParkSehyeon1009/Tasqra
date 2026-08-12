import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { completeOcrReview, getDocument, getOcrPageImage, getOcrReview, setOcrElementExclusion, updateOcrElement } from '../api/document'
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
  const projectQuery = useQuery({ queryKey: ['project-access', projectId], queryFn: () => getProject(projectId), retry: false })
  const documentQuery = useQuery({ queryKey: ['projects', projectId, 'documents', documentId], queryFn: () => getDocument(projectId, documentId) })
  const reviewKey = ['projects', projectId, 'documents', documentId, 'ocr-review']
  const reviewQuery = useQuery({ queryKey: reviewKey, queryFn: () => getOcrReview(projectId, documentId) })
  const review = reviewQuery.data
  const pages = review?.pages ?? []
  const page = pages[pageIndex]
  const effectiveSelectedId = selectedId ?? page?.elements[0]?.id ?? null
  const selected = useMemo(() => page?.elements.find(item => item.id === effectiveSelectedId) ?? null, [page, effectiveSelectedId])
  const draft = selected ? (drafts[selected.id] ?? selected.text) : ''
  const canEdit = projectQuery.data?.role !== 'VIEWER'
  const dirtyChanges = pages.flatMap(item => item.elements.map(element => ({ element, text: drafts[element.id] })).filter(change => change.text !== undefined && change.text !== change.element.text))
  const hasUnsavedChanges = dirtyChanges.length > 0
  const totalElements = pages.reduce((count, item) => count + item.elements.length, 0)
  const changedElements = pages.reduce((count, item) => count + item.elements.filter(element => element.version > 1 || element.is_excluded).length, 0)
  const reviewStatus = getReviewStatus(review?.review_status)


  useEffect(() => {
    const protectChanges = event => { if (hasUnsavedChanges) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', protectChanges)
    return () => window.removeEventListener('beforeunload', protectChanges)
  }, [hasUnsavedChanges])

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

  function goBack() {
    if (!confirmDiscard('저장하지 않은 수정 내용이 있습니다. 문서 목록으로 돌아갈까요?')) return
    navigate('/projects/' + projectId + '/documents')
  }

  const updateMutation = useMutation({
    mutationFn: async changes => {
      const savedChanges = []
      for (const change of changes) {
        try {
          const element = await updateOcrElement(projectId, documentId, change.element.id, change.text, change.element.version)
          savedChanges.push({ element, submittedText: change.text })
        } catch (error) {
          return { savedChanges, error }
        }
      }
      return { savedChanges, error: null }
    },
    onSuccess: async ({ savedChanges, error }) => {
      const updatedById = new Map(savedChanges.map(change => [change.element.id, change.element]))
      if (savedChanges.length) queryClient.setQueryData(reviewKey, current => current ? ({ ...current, ocr_revision: current.ocr_revision + savedChanges.length, review_status: 'IN_PROGRESS', pages: current.pages.map(item => ({ ...item, elements: item.elements.map(element => updatedById.get(element.id) ?? element) })) }) : current)
      setDrafts(current => {
        const next = { ...current }
        savedChanges.forEach(({ element, submittedText }) => {
          if (next[element.id] === submittedText) delete next[element.id]
        })
        return next
      })
      queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true })
      if (error) {
        await reviewQuery.refetch()
        const title = savedChanges.length ? 'OCR 텍스트 일부 저장' : (error.status === 409 ? '수정 내용 충돌' : 'OCR 텍스트 저장 실패')
        const prefix = savedChanges.length ? savedChanges.length + '개 영역은 저장되었습니다. ' : ''
        notify('error', title, prefix + error.message)
        return
      }
      notify('success', 'OCR 텍스트 저장 완료', savedChanges.length + '개 영역의 수정 내용을 저장했습니다.')
    },
    onError: error => { reviewQuery.refetch(); notify('error', error.status === 409 ? '수정 내용 충돌' : 'OCR 텍스트 저장 실패', error.message) },
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
    onSuccess: result => { setDrafts({}); queryClient.setQueryData(reviewKey, result); queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] }); queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true }); notify('success', 'OCR 검수 완료', '검수 결과가 최종 텍스트에 반영되었습니다.') },
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
  const selectedIndex = page.elements.findIndex(element => element.id === effectiveSelectedId)
  return <div className='ocr-review-page'>
    <AppHeader user={user} onLogout={onLogout} notify={notify} project={projectQuery.data}/>
    <header className='ocr-review-toolbar'>
      <div className='ocr-review-title'><button className='back-button' onClick={goBack}>← 문서로 돌아가기</button><h1>{documentQuery.data?.filename ?? 'OCR 검수'}</h1><p>문서 {page.page_number}/{documentPageCount}쪽 · OCR 대상 {pageIndex + 1}/{pages.length}쪽</p></div>
      <div className='ocr-review-toolbar-actions'><span className={'status-badge status-' + reviewStatus.tone} title={reviewStatus.description}>{reviewStatus.label}</span><button className='primary' disabled={!canEdit || completeMutation.isPending || updateMutation.isPending || exclusionMutation.isPending} onClick={completeReview}>{completeMutation.isPending ? '검수 완료 처리 중...' : 'OCR 검수 완료'}</button></div>
    </header>
    <section className='ocr-review-progress' aria-label='OCR 검수 진행 현황'><div><span>OCR 요소</span><strong>{totalElements}개</strong></div><div><span>수정 또는 제외 예정</span><strong>{changedElements}개</strong></div><div><span>현재 선택 영역</span><strong>{selectedIndex >= 0 ? String(selectedIndex + 1) + '/' + page.elements.length : '선택된 항목 없음'}</strong></div><p className={hasUnsavedChanges ? 'has-unsaved' : ''}>{hasUnsavedChanges ? '저장하지 않은 변경 사항이 있습니다.' : '현재 선택 영역의 변경 사항은 저장된 상태입니다.'}</p></section>
    <main className='ocr-review-workspace ocr-review-layout'>
      <section className='ocr-canvas-panel'><div className='ocr-canvas-toolbar'><ConfidenceLegend/><PageNavigator pageIndex={pageIndex} pageCount={pages.length} onChange={changePage}/><div className='ocr-page-context'><strong>원본 문서 {page.page_number}쪽</strong><small>현재 확인 중인 OCR 원본 페이지</small></div></div><OcrCanvas page={page} selectedId={effectiveSelectedId} onSelect={element => selectElement(element, true)}/></section>
      <aside className='ocr-editor-panel'><div className='ocr-editor-heading'><div><h2>인식 텍스트</h2><p>이미지 글자가 본문에 불필요하면 해당 영역을 제외할 수 있습니다.</p></div><span>{page.elements.length}개</span></div><ElementList elements={page.elements} selectedId={effectiveSelectedId} onSelect={selectElement} draft={draft} onDraft={text => selected && setDrafts(current => ({ ...current, [selected.id]: text }))} canEdit={canEdit} saving={updateMutation.isPending || completeMutation.isPending || exclusionMutation.isPending} excluding={exclusionMutation.isPending || updateMutation.isPending || completeMutation.isPending} unsavedCount={dirtyChanges.length} onSave={() => updateMutation.mutate(dirtyChanges)} onToggleExclusion={element => exclusionMutation.mutate(element)}/></aside>
    </main>
  </div>
}

function OcrCanvas({ page, selectedId, onSelect }) {
  const imageQuery = useQuery({ queryKey: ['ocr-page-image', page.id], queryFn: () => getOcrPageImage(page.image_url), staleTime: Infinity })
  if (imageQuery.isPending) return <LoadingState label='원본 이미지를 불러오는 중...'/>
  return <div className='ocr-canvas-scroll'><div className='ocr-canvas'><img src={imageQuery.data} alt={String(page.page_number) + '페이지 원본'}/>{page.elements.map(element => <button key={element.id} title={element.text} aria-label={'OCR 영역: ' + element.text} className={'ocr-box confidence-' + confidenceLevel(element.confidence) + (selectedId === element.id ? ' selected' : '')} style={{ left: String(element.x * 100) + '%', top: String(element.y * 100) + '%', width: String(element.width * 100) + '%', height: String(element.height * 100) + '%' }} onClick={() => onSelect(element)}/>)}</div></div>
}

function PageNavigator({ pageIndex, pageCount, onChange }) {
  return <div className='page-navigator'><button disabled={pageIndex === 0} onClick={() => onChange(pageIndex - 1)}>← 이전</button><strong>OCR 대상 {pageIndex + 1}/{pageCount}</strong><button disabled={pageIndex + 1 >= pageCount} onClick={() => onChange(pageIndex + 1)}>다음 →</button></div>
}

function ConfidenceLegend() { return <div className='confidence-legend'><span className='high'>높음</span><span className='medium'>검토 권장</span><span className='low'>낮음</span><span className='selected-key'>선택 영역</span></div> }

function ElementList({ elements, selectedId, onSelect, draft, onDraft, canEdit, saving, excluding, unsavedCount, onSave, onToggleExclusion }) {
  return <section className='ocr-element-list'><h3>현재 페이지 OCR 영역 <span>{elements.length}</span></h3>{elements.map((element, index) => <article id={'ocr-element-' + element.id} className={(selectedId === element.id ? 'active' : '') + (element.is_excluded ? ' excluded' : '')} key={element.id}><button className='ocr-element-summary' onClick={() => onSelect(element)}><i className={'confidence-dot confidence-' + confidenceLevel(element.confidence)}/><span>{index + 1}. {element.text || '(빈 텍스트)'}</span><small>{element.is_excluded ? '제외 예정' : 'v' + element.version}</small></button>{selectedId === element.id && <div className='inline-ocr-editor'><ConfidenceSummary confidence={element.confidence}/><label>선택 영역 텍스트<textarea value={draft} readOnly={!canEdit} onChange={event => onDraft(event.target.value)}/></label><div className='original-value'><span>최초 인식 원문</span><p>{element.original_text}</p></div><div className='ocr-edit-actions'><button className={element.is_excluded ? 'include-ocr' : 'exclude-ocr'} disabled={!canEdit || excluding} onClick={() => onToggleExclusion(element)}>{element.is_excluded ? '본문에 다시 포함' : '본문에서 제외'}</button></div></div>}</article>)}<div className='ocr-sticky-save' role='status'><span className={unsavedCount ? 'has-unsaved' : ''}>{unsavedCount ? '미저장 변경 ' + unsavedCount + '개' : '변경 사항 저장됨'}</span><button className='primary' disabled={!canEdit || !unsavedCount || saving} onClick={onSave}>{saving ? '저장 중...' : '수정 내용 저장'}</button></div></section>
}

function ConfidenceSummary({ confidence }) { const level = confidenceLevel(confidence); return <div className={'confidence-summary confidence-' + level}><strong>인식 신뢰도</strong><span>{confidence == null ? '정보 없음' : String(Math.round(confidence * 100)) + '%'}</span></div> }
function confidenceLevel(value) { if (value == null || value < .65) return 'low'; if (value < .85) return 'medium'; return 'high' }

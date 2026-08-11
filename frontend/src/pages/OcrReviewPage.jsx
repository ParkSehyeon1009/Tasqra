import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { completeOcrReview, getDocument, getOcrPageImage, getOcrReview, updateOcrElement } from '../api/document'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import '../styles/ocr-review.css'

export default function OcrReviewPage({ user, onLogout, notify }) {
  const { projectId, documentId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [pageIndex, setPageIndex] = useState(0)
  const [selectedId, setSelectedId] = useState(null)
  const [draft, setDraft] = useState('')
  const projectQuery = useQuery({ queryKey: ['project-access', projectId], queryFn: () => getProject(projectId), retry: false })
  const documentQuery = useQuery({ queryKey: ['projects', projectId, 'documents', documentId], queryFn: () => getDocument(projectId, documentId) })
  const reviewKey = ['projects', projectId, 'documents', documentId, 'ocr-review']
  const reviewQuery = useQuery({ queryKey: reviewKey, queryFn: () => getOcrReview(projectId, documentId) })
  const review = reviewQuery.data
  const pages = review?.pages ?? []
  const page = pages[pageIndex]
  const selected = useMemo(() => page?.elements.find(item => item.id === selectedId) ?? null, [page, selectedId])
  const canEdit = projectQuery.data?.role !== 'VIEWER' && review?.review_status !== 'COMPLETED'

  useEffect(() => {
    if (!page) return
    const next = page.elements.find(item => item.id === selectedId) ?? page.elements[0] ?? null
    setSelectedId(next?.id ?? null)
    setDraft(next?.text ?? '')
  }, [page?.id, selected?.version])

  function selectElement(element) {
    setSelectedId(element.id)
    setDraft(element.text)
  }

  const updateMutation = useMutation({
    mutationFn: () => updateOcrElement(projectId, documentId, selected.id, draft, selected.version),
    onSuccess: updated => {
      queryClient.setQueryData(reviewKey, current => ({ ...current, ocr_revision: current.ocr_revision + 1, review_status: current.review_status === 'PENDING' ? 'IN_PROGRESS' : current.review_status, pages: current.pages.map(item => item.id === page.id ? { ...item, elements: item.elements.map(element => element.id === updated.id ? updated : element) } : item) }))
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true })
      notify('success', 'OCR 텍스트 저장 완료', '선택한 영역의 텍스트를 수정했습니다.')
    },
    onError: error => {
      if (error.status === 409) reviewQuery.refetch()
      notify('error', error.status === 409 ? '수정 내용 충돌' : 'OCR 텍스트 저장 실패', error.message)
    },
  })
  const completeMutation = useMutation({
    mutationFn: () => completeOcrReview(projectId, documentId),
    onSuccess: result => {
      queryClient.setQueryData(reviewKey, result)
      queryClient.invalidateQueries({ queryKey: ['projects', Number(projectId), 'documents'] })
      queryClient.invalidateQueries({ queryKey: ['projects', projectId, 'documents', documentId], exact: true })
      notify('success', 'OCR 검수 완료', '검수 결과가 최종 텍스트에 반영되었습니다.')
    },
    onError: error => notify('error', '검수 완료 처리 실패', error.message),
  })

  if (projectQuery.isError) return <div className="center">프로젝트에 접근할 수 없습니다.</div>
  return <div className="ocr-review-page">
    <AppHeader user={user} onLogout={onLogout} notify={notify} project={projectQuery.data}/>
    <header className="ocr-review-toolbar">
      <div><button className="back-button" onClick={() => navigate(`/projects/${projectId}/documents`)}>← 문서로 돌아가기</button><h1>{documentQuery.data?.filename ?? 'OCR 검수'}</h1><p>원본 영역을 선택하고 인식된 텍스트를 확인·수정하세요.</p></div>
      <div className="ocr-review-actions"><StatusBadge status={review?.review_status}/><button className="primary" disabled={!canEdit || completeMutation.isPending} onClick={() => completeMutation.mutate()}>검수 완료</button></div>
    </header>
    {(reviewQuery.isPending || documentQuery.isPending) && <LoadingState label="OCR 검수 데이터를 불러오는 중..."/>}
    {reviewQuery.isError && <div className="ocr-review-error">OCR 검수 데이터를 불러오지 못했습니다.<button onClick={() => reviewQuery.refetch()}>다시 시도</button></div>}
    {review && pages.length === 0 && <div className="ocr-review-empty"><h2>검수할 OCR 영역이 없습니다.</h2><p>텍스트 레이어로 추출된 문서이거나 OCR 좌표가 생성되지 않은 문서입니다.</p></div>}
    {page && <main className="ocr-review-workspace">
      <section className="ocr-canvas-panel"><PageNavigator pageIndex={pageIndex} pageCount={pages.length} onChange={index => { setPageIndex(index); setSelectedId(null) }}/><OcrCanvas page={page} selectedId={selectedId} onSelect={selectElement}/><ConfidenceLegend/></section>
      <aside className="ocr-editor-panel"><h2>인식 텍스트</h2><p className="editor-help">왼쪽 원본에서 박스를 선택하세요.</p>{selected ? <><ConfidenceSummary confidence={selected.confidence}/><label>원본 인식 결과<textarea value={draft} readOnly={!canEdit} onChange={event => setDraft(event.target.value)}/></label><div className="original-value"><span>최초 인식 원문</span><p>{selected.original_text}</p></div><button className="primary save-ocr" disabled={!canEdit || draft === selected.text || updateMutation.isPending} onClick={() => updateMutation.mutate()}>{updateMutation.isPending ? '저장 중...' : '수정 내용 저장'}</button></> : <div className="no-selection">선택할 텍스트 영역이 없습니다.</div>}<ElementList elements={page.elements} selectedId={selectedId} onSelect={selectElement}/></aside>
    </main>}
  </div>
}

function OcrCanvas({ page, selectedId, onSelect }) {
  const imageQuery = useQuery({ queryKey: ['ocr-page-image', page.id], queryFn: () => getOcrPageImage(page.image_url), staleTime: Infinity })
  if (imageQuery.isPending) return <LoadingState label="원본 이미지를 불러오는 중..."/>
  return <div className="ocr-canvas-scroll"><div className="ocr-canvas"><img src={imageQuery.data} alt={`${page.page_number}페이지 원본`}/>{page.elements.map(element => <button key={element.id} title={element.text} aria-label={`OCR 영역: ${element.text}`} className={`ocr-box confidence-${confidenceLevel(element.confidence)}${selectedId === element.id ? ' selected' : ''}`} style={{ left: `${element.x * 100}%`, top: `${element.y * 100}%`, width: `${element.width * 100}%`, height: `${element.height * 100}%` }} onClick={() => onSelect(element)}/>)}</div></div>
}

function PageNavigator({ pageIndex, pageCount, onChange }) { return <div className="page-navigator"><button disabled={pageIndex === 0} onClick={() => onChange(pageIndex - 1)}>← 이전</button><strong>{pageIndex + 1} / {pageCount} 페이지</strong><button disabled={pageIndex + 1 >= pageCount} onClick={() => onChange(pageIndex + 1)}>다음 →</button></div> }
function StatusBadge({ status }) { return <span className={`review-status review-status-${status?.toLowerCase()}`}>{({ PENDING: '검수 대기', IN_PROGRESS: '검수 중', COMPLETED: '검수 완료' })[status] ?? '불러오는 중'}</span> }
function ConfidenceSummary({ confidence }) { const level = confidenceLevel(confidence); return <div className={`confidence-summary confidence-${level}`}><strong>인식 신뢰도</strong><span>{confidence == null ? '정보 없음' : `${Math.round(confidence * 100)}%`}</span></div> }
function ConfidenceLegend() { return <div className="confidence-legend"><span className="high">높음</span><span className="medium">검토 권장</span><span className="low">낮음</span><span className="selected-key">선택 영역</span></div> }
function ElementList({ elements, selectedId, onSelect }) { return <section className="ocr-element-list"><h3>현재 페이지 영역 <span>{elements.length}</span></h3>{elements.map((element, index) => <button className={selectedId === element.id ? 'active' : ''} key={element.id} onClick={() => onSelect(element)}><i className={`confidence-dot confidence-${confidenceLevel(element.confidence)}`}/><span>{index + 1}. {element.text || '(빈 텍스트)'}</span><small>v{element.version}</small></button>)}</section> }
function confidenceLevel(value) { if (value == null || value < .65) return 'low'; if (value < .85) return 'medium'; return 'high' }

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { uploadDocument } from '../api/client'
import { analyzeDocument, getDocument } from '../api/document'
import ErrorBanner from '../components/ErrorBanner'
import Spinner from '../components/Spinner'
import { formatNumber } from '../utils/format'
import './TestPage.css'
import { getAnalysisCategoryLabel } from '../utils/analysisCategory'

const ACCEPTED_EXTENSIONS = ['pdf', 'docx', 'hwpx', 'png', 'jpg', 'jpeg']
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg']
const MAX_FILE_SIZE = 10 * 1024 * 1024

function getExtension(filename = '') {
  return filename.split('.').pop()?.toLowerCase() || ''
}

function validateFile(file) {
  if (!file) return '파일을 선택해 주세요.'

  const extension = getExtension(file.name)
  if (!ACCEPTED_EXTENSIONS.includes(extension)) {
    return 'PDF, DOCX, HWPX, PNG, JPG, JPEG 파일만 업로드할 수 있습니다.'
  }

  if (file.size > MAX_FILE_SIZE) {
    return '파일은 최대 10MB까지 업로드할 수 있습니다.'
  }

  return null
}

function ResultCard({ analysis }) {
  if (analysis.analyzer_type === 'summary') {
    return (
      <article className="analysis-result analysis-result--summary">
        <div className="analysis-result__head">
          <span className="analysis-result__eyebrow">요약 결과</span>
          <span className="analysis-result__meta">
            {analysis.provider} · {analysis.model_name}
          </span>
        </div>
        <p className="analysis-result__text">
          {analysis.result?.summary || '요약 결과가 비어 있습니다.'}
        </p>
      </article>
    )
  }

  if (analysis.analyzer_type === 'category') {
    return (
      <article className="analysis-result analysis-result--category">
        <div className="analysis-result__head">
          <span className="analysis-result__eyebrow">분류 결과</span>
          <span className="analysis-result__meta">
            {analysis.provider} · {analysis.model_name}
          </span>
        </div>
        <strong className="analysis-result__category">
          {getAnalysisCategoryLabel(analysis.result?.category)}
        </strong>
        <div className="analysis-result__reason">
          <span>분류 사유</span>
          <p>{analysis.result?.reason || '분류 사유가 제공되지 않았습니다.'}</p>
        </div>
      </article>
    )
  }

  return (
    <article className="analysis-result">
      <pre>{JSON.stringify(analysis.result, null, 2)}</pre>
    </article>
  )
}

export default function TestPage() {
  const fileInputRef = useRef(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [document, setDocument] = useState(null)
  const [analyses, setAnalyses] = useState([])
  const [checkedTypes, setCheckedTypes] = useState({ summary: true, category: true })
  const [uploading, setUploading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState(null)

  const previewUrl = useMemo(
    () => (selectedFile ? URL.createObjectURL(selectedFile) : ''),
    [selectedFile],
  )

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  function chooseFile(file) {
    const message = validateFile(file)
    if (message) {
      setError(new Error(message))
      return
    }

    setSelectedFile(file)
    setDocument(null)
    setAnalyses([])
    setError(null)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    chooseFile(event.dataTransfer.files?.[0])
  }

  function resetSelection() {
    setSelectedFile(null)
    setDocument(null)
    setAnalyses([])
    setError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleUpload() {
    const message = validateFile(selectedFile)
    if (message) {
      setError(new Error(message))
      return
    }

    setUploading(true)
    setError(null)
    setDocument(null)
    setAnalyses([])

    try {
      const uploaded = await uploadDocument(selectedFile)
      const detail = await getDocument(uploaded.id)
      setDocument({ ...uploaded, ...detail })
    } catch (err) {
      setError(err)
    } finally {
      setUploading(false)
    }
  }

  function toggleType(type) {
    setCheckedTypes((current) => ({ ...current, [type]: !current[type] }))
  }

  async function handleAnalyze() {
    if (!document) return

    const selectedTypes = Object.entries(checkedTypes)
      .filter(([, checked]) => checked)
      .map(([type]) => type)

    if (selectedTypes.length === 0) {
      setError(new Error('요약 또는 분류 중 하나 이상을 선택해 주세요.'))
      return
    }

    setAnalyzing(true)
    setError(null)

    try {
      const result = await analyzeDocument(document.project_id, document.id, selectedTypes)
      setAnalyses(result.analyses)
    } catch (err) {
      setError(err)
    } finally {
      setAnalyzing(false)
    }
  }

  const extension = getExtension(selectedFile?.name)
  const isImage = IMAGE_EXTENSIONS.includes(extension)
  const isPdf = extension === 'pdf'

  return (
    <div className="c-scope upload-page">
      <header className="upload-page__header">
        <div>
          <p className="upload-page__eyebrow">DOCUMENT WORKSPACE</p>
          <h1>문서 업로드 및 분석</h1>
          <p>문서를 올리고 OCR 원문과 AI 분석 결과를 한 화면에서 확인하세요.</p>
        </div>
        <Link to="/documents" className="upload-page__back">문서 목록으로</Link>
      </header>

      <ErrorBanner error={error} />

      <section className="upload-section" aria-labelledby="upload-title">
        <div className="section-heading">
          <span className="section-step">01</span>
          <div>
            <h2 id="upload-title">파일 선택</h2>
            <p>파일을 끌어놓거나 직접 선택한 뒤 전송해 주세요.</p>
          </div>
        </div>

        <input
          ref={fileInputRef}
          className="sr-only"
          type="file"
          accept=".pdf,.docx,.hwpx,.png,.jpg,.jpeg"
          onChange={(event) => chooseFile(event.target.files?.[0])}
        />

        <div
          className={`drop-zone${dragging ? ' drop-zone--active' : ''}${selectedFile ? ' drop-zone--selected' : ''}`}
          onDragEnter={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false)
          }}
          onDrop={handleDrop}
        >
          <div className="drop-zone__icon" aria-hidden="true">↑</div>
          {selectedFile ? (
            <div className="drop-zone__file">
              <strong>{selectedFile.name}</strong>
              <span>{extension.toUpperCase()} · {(selectedFile.size / 1024 / 1024).toFixed(2)}MB</span>
            </div>
          ) : (
            <div>
              <strong>여기에 파일을 끌어다 놓으세요</strong>
              <span>PDF, DOCX, HWPX, PNG, JPG · 최대 10MB</span>
            </div>
          )}
          <button
            type="button"
            className="upload-button upload-button--secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {selectedFile ? '다른 파일 선택' : '파일 선택'}
          </button>
        </div>

        {selectedFile && !uploading && !document && (
          <div className="upload-actions">
            <button type="button" className="text-button" onClick={resetSelection}>
              선택 취소
            </button>
            <button type="button" className="upload-button" onClick={handleUpload}>
              업로드 및 추출
            </button>
          </div>
        )}

        {uploading && (
          <div className="processing-panel">
            <Spinner label="문서를 처리하고 있습니다..." />
            <p>문서의 텍스트와 이미지를 분석하고 있습니다. 잠시만 기다려 주세요.</p>
          </div>
        )}
      </section>

      {document && (
        <>
          <section className="upload-section" aria-labelledby="compare-title">
            <div className="section-heading section-heading--between">
              <div className="section-heading__group">
                <span className="section-step">02</span>
                <div>
                  <h2 id="compare-title">OCR 결과 비교</h2>
                  <p>업로드한 원본과 추출된 텍스트를 나란히 확인하세요.</p>
                </div>
              </div>
              <div className="document-stats">
                <span>{document.extract_method}</span>
                <span>{formatNumber(document.char_count)}자</span>
                <span>{formatNumber(document.page_count)}페이지</span>
              </div>
            </div>

            <div className="comparison-grid">
              <article className="preview-card">
                <div className="preview-card__head">
                  <span>업로드 원본</span>
                  <strong>{selectedFile?.name}</strong>
                </div>
                <div className="preview-card__body">
                  {isImage && <img src={previewUrl} alt={`${selectedFile.name} 미리보기`} />}
                  {isPdf && <object data={previewUrl} type="application/pdf" aria-label="PDF 미리보기" />}
                  {!isImage && !isPdf && (
                    <div className="file-placeholder">
                      <span>{extension.toUpperCase()}</span>
                      <strong>{selectedFile?.name}</strong>
                      <p>이 형식은 브라우저 미리보기를 지원하지 않습니다.</p>
                    </div>
                  )}
                </div>
              </article>

              <article className="preview-card">
                <div className="preview-card__head">
                  <span>추출 텍스트</span>
                  <strong>{formatNumber(document.extracted_text?.length || 0)}자</strong>
                </div>
                <pre className="extracted-text">
                  {document.extracted_text || '추출된 텍스트가 없습니다.'}
                </pre>
              </article>
            </div>
          </section>

          <section className="upload-section" aria-labelledby="analysis-title">
            <div className="section-heading">
              <span className="section-step">03</span>
              <div>
                <h2 id="analysis-title">AI 분석</h2>
                <p>필요한 분석을 선택해 한 번에 실행할 수 있습니다.</p>
              </div>
            </div>

            <div className="analysis-controls">
              <label className={`analysis-option${checkedTypes.summary ? ' analysis-option--checked' : ''}`}>
                <input
                  type="checkbox"
                  checked={checkedTypes.summary}
                  onChange={() => toggleType('summary')}
                />
                <span>
                  <strong>핵심 요약</strong>
                  <small>문서의 핵심 내용을 간결하게 정리합니다.</small>
                </span>
              </label>

              <label className={`analysis-option${checkedTypes.category ? ' analysis-option--checked' : ''}`}>
                <input
                  type="checkbox"
                  checked={checkedTypes.category}
                  onChange={() => toggleType('category')}
                />
                <span>
                  <strong>문서 분류</strong>
                  <small>카테고리와 판단 사유를 함께 제공합니다.</small>
                </span>
              </label>

              <button
                type="button"
                className="upload-button analysis-run"
                onClick={handleAnalyze}
                disabled={analyzing}
              >
                {analyzing ? '분석 중…' : '선택한 분석 진행'}
              </button>
            </div>

            {analyzing && (
              <div className="processing-panel processing-panel--compact">
                <Spinner label="선택한 AI 분석을 진행하고 있습니다…" />
              </div>
            )}

            {analyses.length > 0 && (
              <div className="analysis-results">
                {analyses.map((analysis) => (
                  <ResultCard key={analysis.id} analysis={analysis} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

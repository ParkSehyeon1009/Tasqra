import PageHeading from '../../components/common/PageHeading'

export default function DocumentsView({ documents, canEdit, onUpload }) {
  const action = canEdit ? <button className="primary" onClick={onUpload}>문서 업로드</button> : null
  return <><PageHeading eyebrow="PROJECT DOCUMENTS" title="문서" description="업로드된 문서와 처리 상태를 확인합니다." action={action}/>
    <section className="panel table-panel"><div className="panel-head"><h2>전체 문서</h2><span>{documents.length}건</span></div>
      {documents.length ? <DocumentList documents={documents}/> : <EmptyDocuments onUpload={onUpload} canEdit={canEdit}/>}</section></>
}

function DocumentList({ documents }) {
  return <ul className="document-list">{documents.map(document => <li key={document.id}><span className="file-icon">{document.file_type?.toUpperCase()}</span><div><strong>{document.filename}</strong><small>{document.extract_method || '처리 완료'} · {document.char_count?.toLocaleString() || 0}자</small></div><span className="type-pill">{document.document_type || '미분류'}</span><span className="complete-pill">{document.status}</span><time>{new Date(document.created_at).toLocaleDateString()}</time></li>)}</ul>
}

function EmptyDocuments({ onUpload, canEdit }) {
  return <div className="drop-zone"><b>↑</b><h2>문서를 업로드해 시작하세요.</h2><p>PDF · DOCX · HWPX · JPG · PNG</p>{canEdit && <button onClick={onUpload}>파일 선택</button>}</div>
}

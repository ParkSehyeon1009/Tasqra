import '../../styles/dialog.css'

export default function ConfirmDialog({ open, title, message, confirmLabel = '확인', danger = false, onConfirm, onCancel }) {
  if (!open) return null
  return <div className="dialog-backdrop" role="presentation" onMouseDown={onCancel}><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" onMouseDown={event => event.stopPropagation()}><h2 id="confirm-title">{title}</h2><p>{message}</p><div><button onClick={onCancel}>취소</button><button className={danger ? 'danger' : 'primary'} onClick={onConfirm}>{confirmLabel}</button></div></section></div>
}

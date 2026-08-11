import { useState } from 'react'
import '../../styles/dialog.css'

export default function ConfirmDialog({ open, title, message, confirmLabel = '확인', danger = false, confirmationText, onConfirm, onCancel }) {
  const [typedText, setTypedText] = useState('')

  if (!open) return null
  const confirmationMatched = !confirmationText || typedText === confirmationText
  const cancel = () => { setTypedText(''); onCancel() }
  const confirm = () => { setTypedText(''); onConfirm() }
  return <div className="dialog-backdrop" role="presentation" onMouseDown={cancel}><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" onMouseDown={event => event.stopPropagation()}>
    <h2 id="confirm-title">{title}</h2><p>{message}</p>
    {confirmationText && <label className="confirm-dialog__verification"><span>계속하려면 <strong>{confirmationText}</strong>을(를) 입력하세요.</span><input value={typedText} onChange={event => setTypedText(event.target.value)} autoComplete="off" autoFocus/></label>}
    <div><button onClick={cancel}>취소</button><button className={danger ? 'danger' : 'primary'} onClick={confirm} disabled={!confirmationMatched}>{confirmLabel}</button></div>
  </section></div>
}

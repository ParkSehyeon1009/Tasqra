import { useEffect, useId, useRef, useState } from 'react'
import '../../styles/dialog.css'

export default function ConfirmDialog({ open, title, message, confirmLabel = '확인', danger = false, confirmationText, onConfirm, onCancel }) {
  const [typedText, setTypedText] = useState('')
  const dialogRef = useRef(null)
  const cancelRef = useRef(null)
  const previousFocusRef = useRef(null)
  const onCancelRef = useRef(onCancel)
  const titleId = useId()
  const messageId = useId()

  useEffect(() => { onCancelRef.current = onCancel }, [onCancel])

  useEffect(() => {
    if (!open) return
    previousFocusRef.current = document.activeElement
    requestAnimationFrame(() => {
      setTypedText('')
      dialogRef.current?.querySelector('input')?.focus() ?? cancelRef.current?.focus()
    })
    const handleKeyDown = event => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setTypedText('')
        onCancelRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll('button:not([disabled]), input:not([disabled])')
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      requestAnimationFrame(() => previousFocusRef.current?.focus())
    }
  }, [open])

  if (!open) return null
  const confirmationMatched = !confirmationText || typedText === confirmationText
  const cancel = () => { setTypedText(''); onCancel() }
  const confirm = () => { setTypedText(''); onConfirm() }
  return <div className="dialog-backdrop" role="presentation" onMouseDown={cancel}><section className="confirm-dialog" ref={dialogRef} role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={messageId} onMouseDown={event => event.stopPropagation()}>
    <h2 id={titleId}>{title}</h2><p id={messageId}>{message}</p>
    {confirmationText && <label className="confirm-dialog__verification"><span>계속하려면 <strong>{confirmationText}</strong>을(를) 입력하세요.</span><input value={typedText} onChange={event => setTypedText(event.target.value)} autoComplete="off" autoFocus/></label>}
    <div><button ref={cancelRef} onClick={cancel}>취소</button><button className={danger ? 'danger' : 'primary'} onClick={confirm} disabled={!confirmationMatched}>{confirmLabel}</button></div>
  </section></div>
}

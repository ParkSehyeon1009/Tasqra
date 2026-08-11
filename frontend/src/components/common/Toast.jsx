export default function Toast({ toast, onClose }) {
  if (!toast) return null
  return <div className={`toast toast--${toast.type}`} role="status">
    <span className="toast__icon">{toast.type === 'success' ? '✓' : '!'}</span>
    <div><strong>{toast.title}</strong><p>{toast.message}</p></div>
    <button onClick={onClose} aria-label="알림 닫기">×</button>
  </div>
}

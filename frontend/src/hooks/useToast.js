import { useCallback, useEffect, useRef, useState } from 'react'

export function useToast() {
  const [toast, setToast] = useState(null)
  const timer = useRef(null)

  const closeToast = useCallback(() => setToast(null), [])
  const notify = useCallback((type, title, message) => {
    clearTimeout(timer.current)
    setToast({ type, title, message })
    timer.current = setTimeout(closeToast, 3500)
  }, [closeToast])

  useEffect(() => () => clearTimeout(timer.current), [])
  return { toast, notify, closeToast }
}

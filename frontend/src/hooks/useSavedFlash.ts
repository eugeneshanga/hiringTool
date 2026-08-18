import { useEffect, useRef, useState } from 'react'

/**
 * Tracks a brief "Saved" confirmation to show next to a save button.
 * Call `flash()` right after a save succeeds; `saved` flips back to false
 * on its own a couple seconds later.
 */
export function useSavedFlash(durationMs = 2000) {
  const [saved, setSaved] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  function flash() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    setSaved(true)
    timeoutRef.current = setTimeout(() => setSaved(false), durationMs)
  }

  return { saved, flash }
}

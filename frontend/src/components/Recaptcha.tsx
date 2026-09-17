import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

declare global {
  interface Window {
    grecaptcha?: {
      render: (
        container: HTMLElement,
        params: { sitekey: string; callback: (token: string) => void; 'expired-callback': () => void },
      ) => number
      reset: (widgetId?: number) => void
    }
  }
}

const SCRIPT_URL = 'https://www.google.com/recaptcha/api.js'

// Shared across every mount (StrictMode double-mounts in dev, and this
// could in principle render more than once on a page) - Google's script
// only needs loading once; a second <script> tag would just refetch it.
let scriptLoadPromise: Promise<void> | null = null

function loadScript(): Promise<void> {
  if (window.grecaptcha) return Promise.resolve()
  if (!scriptLoadPromise) {
    scriptLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = SCRIPT_URL
      script.async = true
      script.defer = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('Failed to load reCAPTCHA'))
      document.head.appendChild(script)
    })
  }
  return scriptLoadPromise
}

export interface RecaptchaHandle {
  /** Clears the current solve (a failed login needs a fresh one - Google's
   * tokens are single-use) and resets the checkbox to its unsolved state. */
  reset: () => void
}

interface RecaptchaProps {
  siteKey: string
  onChange: (token: string | null) => void
}

/** The "I'm not a robot" checkbox widget on the recruiter login form
 * (LoginPage.tsx) - see config.py's RECAPTCHA_SECRET_KEY docstring for the
 * backend half. A thin wrapper around Google's own api.js (loaded once,
 * see loadScript above) rather than a third-party npm package - this app
 * otherwise has zero UI dependencies beyond react/react-dom/react-router,
 * and the widget itself is simple enough not to need one. */
export const Recaptcha = forwardRef<RecaptchaHandle, RecaptchaProps>(function Recaptcha(
  { siteKey, onChange },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetIdRef = useRef<number | null>(null)

  useImperativeHandle(ref, () => ({
    reset() {
      if (widgetIdRef.current !== null) window.grecaptcha?.reset(widgetIdRef.current)
      onChange(null)
    },
  }))

  useEffect(() => {
    let cancelled = false
    loadScript()
      .then(() => {
        if (cancelled || !containerRef.current || widgetIdRef.current !== null) return
        widgetIdRef.current = window.grecaptcha!.render(containerRef.current, {
          sitekey: siteKey,
          callback: (token) => onChange(token),
          'expired-callback': () => onChange(null),
        })
      })
      .catch(() => {
        // Fails open on the frontend - LoginPage still requires a token
        // before enabling submit, so a candidate/recruiter just can't log
        // in if Google's script is unreachable (rare, and consistent with
        // the backend's own fail-closed verification below).
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div ref={containerRef} />
})

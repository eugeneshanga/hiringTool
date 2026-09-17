import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'

declare global {
  interface Window {
    grecaptcha?: {
      ready: (callback: () => void) => void
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

// The <script> tag's own onload firing only means api.js finished
// downloading - grecaptcha's actual API (specifically .render) isn't
// guaranteed ready until grecaptcha.ready() says so. Calling .render()
// straight off the script's onload is a real, well-known race (usually
// works, sometimes silently doesn't) - this is why Google's own docs
// recommend ready() rather than the script's onload for anything beyond
// the auto-render (data-sitekey div) path.
function whenGrecaptchaReady(): Promise<void> {
  return loadScript().then(
    () => new Promise((resolve) => window.grecaptcha!.ready(() => resolve())),
  )
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
    whenGrecaptchaReady()
      .then(() => {
        if (cancelled || !containerRef.current || widgetIdRef.current !== null) return
        widgetIdRef.current = window.grecaptcha!.render(containerRef.current, {
          sitekey: siteKey,
          callback: (token) => onChange(token),
          'expired-callback': () => onChange(null),
        })
      })
      .catch((err) => {
        // LoginPage still requires a token before enabling submit, so a
        // recruiter just can't log in if this fails (rare - Google
        // unreachable, or a real bug here) - consistent with the backend's
        // own fail-closed verification. Logged rather than swallowed so
        // that failure is actually visible in DevTools instead of just
        // "the checkbox never showed up, no idea why".
        console.error('reCAPTCHA failed to load/render', err)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The container itself stretches full-width as a flex column child
  // (LoginPage's .login-card), but the compact widget it renders (164px)
  // is narrower than that - center it rather than leaving it flush left
  // while every other field spans the full width.
  return <div ref={containerRef} style={{ display: 'flex', justifyContent: 'center' }} />
})

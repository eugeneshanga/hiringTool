import { useRef, useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ApiError } from '../api/client'
import { usePageTitle } from '../hooks/usePageTitle'
import { Recaptcha, type RecaptchaHandle } from '../components/Recaptcha'

// Unset in local dev unless frontend/.env has it (see config.py's
// RECAPTCHA_SECRET_KEY docstring) - the widget/requirement simply doesn't
// render at all then, same "unconfigured = feature no-ops" pattern as the
// backend half.
const RECAPTCHA_SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY as string | undefined

export function LoginPage() {
  usePageTitle('Sign In - HiringTool')

  const { user, login, sessionExpired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [recaptchaToken, setRecaptchaToken] = useState<string | null>(null)
  const recaptchaRef = useRef<RecaptchaHandle>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) {
    const dest = (location.state as { from?: string } | null)?.from ?? '/dashboard'
    return <Navigate to={dest} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password, recaptchaToken)
      navigate('/dashboard')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
      // A token is single-use - whether it was ever sent or the login
      // itself just failed, the recruiter needs a fresh solve to retry.
      recaptchaRef.current?.reset()
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>HiringTool</h1>
        <p className="subtle">Sign in to continue</p>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {RECAPTCHA_SITE_KEY && (
          <Recaptcha ref={recaptchaRef} siteKey={RECAPTCHA_SITE_KEY} onChange={setRecaptchaToken} />
        )}
        {/* A submit error is more specific/recent than a stale expiry
            notice from before this attempt - it takes priority rather than
            showing both at once. */}
        {error ? (
          <div className="error-banner">{error}</div>
        ) : (
          sessionExpired && (
            <div className="error-banner">Your session expired — please sign in again.</div>
          )
        )}
        <button type="submit" disabled={submitting || (!!RECAPTCHA_SITE_KEY && !recaptchaToken)}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}

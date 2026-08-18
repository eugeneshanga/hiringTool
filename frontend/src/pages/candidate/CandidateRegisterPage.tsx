import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useCandidateAuth } from '../../candidateAuth/CandidateAuthContext'
import { ApiError } from '../../api/client'

export function CandidateRegisterPage() {
  const { candidate, register } = useCandidateAuth()
  const navigate = useNavigate()
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (candidate) {
    return <Navigate to="/apply" replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setSubmitting(true)
    try {
      await register({
        first_name: firstName,
        last_name: lastName,
        email,
        phone: phone || undefined,
        password,
      })
      navigate('/apply')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>HiringTool</h1>
        <p className="subtle">Create a candidate account</p>

        <div className="form-row">
          <label>
            First name
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required autoFocus />
          </label>
          <label>
            Last name
            <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
          </label>
        </div>

        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>

        <label>
          Phone number
          <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>
        <label>
          Confirm password
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            minLength={8}
            required
          />
        </label>
        {error && <div className="error-banner">{error}</div>}
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
        <p className="subtle">
          Already have an account? <Link to="/apply/login">Sign in</Link>
        </p>
        <p className="subtle sms-consent">
          By providing a phone number, I agree to receive text messages from Florence Precious Home
          Care for account notifications.
        </p>
      </form>
    </div>
  )
}

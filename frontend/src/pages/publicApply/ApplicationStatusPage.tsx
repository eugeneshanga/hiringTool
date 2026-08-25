import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { publicApplyApi, publicErrorMessage } from '../../api/publicApplyClient'
import type { ApplicationStatus } from '../../api/types'

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

/** Public, read-only lookup (GET /api/status) — reached via the link in the
 * confirmation email (?code=...), or by hand with a confirmation code or
 * phone number for anyone who didn't keep that email. See routes/status.py
 * for why a phone lookup only ever matches a booking made through this same
 * flow, never an arbitrary recruiter-created interview. */
export function ApplicationStatusPage() {
  const [searchParams] = useSearchParams()
  const initialCode = searchParams.get('code') ?? ''

  const [code, setCode] = useState(initialCode)
  const [phone, setPhone] = useState('')
  const [result, setResult] = useState<ApplicationStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function runLookup(params: { code?: string; phone?: string }) {
    setLoading(true)
    setError(null)
    try {
      setResult(await publicApplyApi.getStatus(params))
    } catch (err) {
      setResult(null)
      setError(publicErrorMessage(err, 'No matching application found.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (initialCode) runLookup({ code: initialCode })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmedCode = code.trim()
    const trimmedPhone = phone.trim()
    if (!trimmedCode && !trimmedPhone) {
      setError('Enter a confirmation code or phone number.')
      return
    }
    runLookup(trimmedCode ? { code: trimmedCode } : { phone: trimmedPhone })
  }

  return (
    <div className="public-page">
      <div className="card public-card">
        <h1>Application status</h1>
        <form className="form" onSubmit={handleSubmit}>
          <label>
            Confirmation code
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. 7X4KMPQ2R" />
          </label>
          <p className="subtle" style={{ textAlign: 'center' }}>or</p>
          <label>
            Phone number
            <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? 'Looking up…' : 'Look up'}
          </button>
        </form>

        {error && <div className="error-banner">{error}</div>}

        {result && (
          <div className="status-result">
            <h2>{result.stage_name}</h2>
            <p>
              {result.candidate_name} — {result.job_title}
            </p>
            <p>
              Scheduled for <strong>{formatDateTime(result.scheduled_start)}</strong>
            </p>
            {result.meeting_link && (
              <p>
                Meeting link: <a href={result.meeting_link} target="_blank" rel="noreferrer">{result.meeting_link}</a>
              </p>
            )}
            <p className="subtle">Confirmation code: {result.confirmation_code}</p>
          </div>
        )}
      </div>
    </div>
  )
}

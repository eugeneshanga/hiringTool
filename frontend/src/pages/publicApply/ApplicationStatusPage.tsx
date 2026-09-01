import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { publicApplyApi, publicErrorMessage } from '../../api/publicApplyClient'
import { usePageTitle } from '../../hooks/usePageTitle'
import type { ApplicationStatus, CandidateDocumentChecklistItem } from '../../api/types'

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

// Fixed, hardcoded on the frontend rather than displaying whatever
// publicApplyApi.resendCode's response happens to contain - the backend
// already guarantees an identical response either way (see routes/
// status.py's resend_confirmation_code), but keeping the copy fixed here
// too means the frontend can never accidentally start branching on
// response content if that ever changed, which is the whole point of the
// backend never revealing a match either.
const RESEND_CODE_MESSAGE =
  "If that email matches an application with a scheduled interview, we've sent the confirmation code to it."

/** Public, read-only lookup (GET /api/status) — reached via the link in the
 * confirmation email (?code=...), or by hand with a confirmation code for
 * anyone who didn't keep that email. Code-only, deliberately - see
 * routes/status.py's module docstring for why this doesn't also accept a
 * phone number or email as a second direct-lookup identifier (both are too
 * low-entropy to safely return a match directly the way a code can).
 *
 * Also the only place a candidate ever interacts with the app after
 * applying — there's no candidate login (see models.py's Candidate
 * docstring for the removed CandidateAccount). Once a lookup succeeds, the
 * same code that found it also gates uploading onboarding documents
 * (POST /api/status/documents) — see handleUpload below. A candidate who
 * doesn't have their code at all uses the email form instead (see
 * handleResendCode) - safe specifically because it never returns a match
 * directly, only ever triggers an email. */
export function ApplicationStatusPage() {
  usePageTitle('Application Status')

  const [searchParams] = useSearchParams()
  const initialCode = searchParams.get('code') ?? ''

  const [code, setCode] = useState(initialCode)
  const [result, setResult] = useState<ApplicationStatus | null>(null)
  // The code the *current* result was actually looked up with — reused to
  // authenticate each document upload.
  const [lookupCode, setLookupCode] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [uploadingItemId, setUploadingItemId] = useState<number | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const [showEmailForm, setShowEmailForm] = useState(false)
  const [emailForCode, setEmailForCode] = useState('')
  const [resendSubmitting, setResendSubmitting] = useState(false)
  // Distinct from RESEND_CODE_MESSAGE: this is only ever a real request
  // failure (network error, rate limit) - never anything derived from
  // whether resendCode found a match, since that's never surfaced at all.
  const [resendRequestError, setResendRequestError] = useState<string | null>(null)
  const [resendSubmitted, setResendSubmitted] = useState(false)

  async function runLookup(lookupCode: string) {
    setLoading(true)
    setError(null)
    setUploadError(null)
    try {
      const data = await publicApplyApi.getStatus(lookupCode)
      setResult(data)
      setLookupCode(lookupCode)
    } catch (err) {
      setResult(null)
      setLookupCode(null)
      setError(publicErrorMessage(err, 'No matching application found.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (initialCode) runLookup(initialCode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmedCode = code.trim()
    if (!trimmedCode) {
      setError('Enter your confirmation code.')
      return
    }
    runLookup(trimmedCode)
  }

  async function handleUpload(itemId: number, e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !lookupCode) return
    setUploadingItemId(itemId)
    setUploadError(null)
    try {
      const submission = await publicApplyApi.uploadStatusDocument(lookupCode, itemId, file)
      // Merge the fresh submission into the existing result rather than
      // re-running the whole lookup — same UX reasoning as
      // DocumentChecklist.tsx's loadDocs(), just without a second request.
      setResult((prev) =>
        prev
          ? {
              ...prev,
              onboarding_documents: prev.onboarding_documents.map((item) =>
                item.item_id === itemId ? { ...item, submission } : item,
              ),
            }
          : prev,
      )
    } catch (err) {
      setUploadError(publicErrorMessage(err, 'Failed to upload document'))
    } finally {
      setUploadingItemId(null)
    }
  }

  async function handleResendCode(e: FormEvent) {
    e.preventDefault()
    const trimmedEmail = emailForCode.trim()
    if (!trimmedEmail) return
    setResendSubmitting(true)
    setResendRequestError(null)
    try {
      await publicApplyApi.resendCode(trimmedEmail)
      // Deliberately ignore whatever the response actually contains - see
      // RESEND_CODE_MESSAGE. Shown regardless of whether a match existed.
      setResendSubmitted(true)
    } catch (err) {
      // A real failure (network error, the 5/hour rate limit) - not a
      // "no match" signal, since a miss returns this same 200 as a hit.
      setResendRequestError(publicErrorMessage(err))
    } finally {
      setResendSubmitting(false)
    }
  }

  function renderChecklistItem(item: CandidateDocumentChecklistItem) {
    return (
      <div key={item.item_id} className="document-row">
        <strong>{item.description}</strong>
        <p className="subtle">{item.submission ? item.submission.original_filename : 'No submission yet'}</p>
        <label className="link-button">
          {uploadingItemId === item.item_id ? 'Uploading…' : item.submission ? 'Replace ⬆' : 'Upload ⬆'}
          <input
            type="file"
            hidden
            accept=".pdf,.docx,.jpg,.jpeg,.png"
            onChange={(e) => handleUpload(item.item_id, e)}
            disabled={uploadingItemId === item.item_id}
          />
        </label>
      </div>
    )
  }

  const requiredItems = result?.onboarding_documents.filter((item) => item.required) ?? []
  const optionalItems = result?.onboarding_documents.filter((item) => !item.required) ?? []

  return (
    <div className="public-page">
      <div className="card public-card">
        <h1>Application status</h1>
        <form className="form" onSubmit={handleSubmit}>
          <label>
            Confirmation code
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. 7X4KMPQ2R" />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? 'Looking up…' : 'Look up'}
          </button>
        </form>

        <div className="forgot-code">
          {!showEmailForm ? (
            <button type="button" className="link-button" onClick={() => setShowEmailForm(true)}>
              Don't have your code?
            </button>
          ) : resendSubmitted ? (
            <p className="subtle">{RESEND_CODE_MESSAGE}</p>
          ) : (
            <form className="form" onSubmit={handleResendCode}>
              <label>
                Email you applied with
                <input
                  type="email"
                  value={emailForCode}
                  onChange={(e) => setEmailForCode(e.target.value)}
                  required
                  autoFocus
                />
              </label>
              {resendRequestError && <div className="error-banner">{resendRequestError}</div>}
              <button type="submit" disabled={resendSubmitting}>
                {resendSubmitting ? 'Sending…' : 'Send my code'}
              </button>
            </form>
          )}
        </div>

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

        {result && result.onboarding_documents.length > 0 && (
          <div className="status-result">
            <h2>Onboarding documents</h2>
            <p className="subtle">Accepted formats: PDF, DOCX, JPG, PNG.</p>
            {uploadError && <div className="error-banner">{uploadError}</div>}
            {requiredItems.length > 0 && (
              <>
                <p className="subtle">Required</p>
                <div className="document-list">{requiredItems.map(renderChecklistItem)}</div>
              </>
            )}
            {optionalItems.length > 0 && (
              <>
                <p className="subtle">Optional</p>
                <div className="document-list">{optionalItems.map(renderChecklistItem)}</div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

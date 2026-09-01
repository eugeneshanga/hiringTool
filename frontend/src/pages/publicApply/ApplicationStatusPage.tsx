import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { publicApplyApi, publicErrorMessage } from '../../api/publicApplyClient'
import type { ApplicationStatus, CandidateDocumentChecklistItem } from '../../api/types'

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

/** Public, read-only lookup (GET /api/status) — reached via the link in the
 * confirmation email (?code=...), or by hand with a confirmation code or
 * phone number for anyone who didn't keep that email. See routes/status.py
 * for why a phone lookup only ever matches a booking made through this same
 * flow, never an arbitrary recruiter-created interview.
 *
 * Also the only place a candidate ever interacts with the app after
 * applying — there's no candidate login (see models.py's Candidate
 * docstring for the removed CandidateAccount). Once a lookup succeeds, the
 * same code/phone that found it also gates uploading onboarding documents
 * (POST /api/status/documents) — see handleUpload below. */
export function ApplicationStatusPage() {
  const [searchParams] = useSearchParams()
  const initialCode = searchParams.get('code') ?? ''

  const [code, setCode] = useState(initialCode)
  const [phone, setPhone] = useState('')
  const [result, setResult] = useState<ApplicationStatus | null>(null)
  // Whichever of code/phone the *current* result was actually looked up
  // with — reused to authenticate each document upload, since re-sending
  // both fields regardless of which one the visitor filled in would send a
  // stale/empty value for the other.
  const [lookupParams, setLookupParams] = useState<{ code?: string; phone?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [uploadingItemId, setUploadingItemId] = useState<number | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  async function runLookup(params: { code?: string; phone?: string }) {
    setLoading(true)
    setError(null)
    setUploadError(null)
    try {
      const data = await publicApplyApi.getStatus(params)
      setResult(data)
      setLookupParams(params)
    } catch (err) {
      setResult(null)
      setLookupParams(null)
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

  async function handleUpload(itemId: number, e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !lookupParams) return
    setUploadingItemId(itemId)
    setUploadError(null)
    try {
      const submission = await publicApplyApi.uploadStatusDocument(lookupParams, itemId, file)
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

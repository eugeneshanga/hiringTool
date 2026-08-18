import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useSavedFlash } from '../hooks/useSavedFlash'
import { copyText } from '../lib/clipboard'
import { CandidateInfoCard } from './candidateDetails/CandidateInfoCard'
import { StageTabs } from './candidateDetails/StageTabs'
import { DocumentChecklist } from './candidateDetails/DocumentChecklist'
import { ScreeningAnswers } from './candidateDetails/ScreeningAnswers'
import type { CandidateDetail } from '../api/types'

/** Fetches the candidate and hosts the shared error banner + Close/Share
 * toolbar; each section below owns its own local state and fetches, and
 * reports changes back up via onCandidateChange so every section stays in
 * sync with the others (e.g. editing contact info also updates the header). */
export function CandidateDetailsPage() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const shareFlash = useSavedFlash(1500)

  useEffect(() => {
    if (!candidateId) return
    setLoading(true)
    setError(null)
    api
      .getCandidate(Number(candidateId))
      .then(setCandidate)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load candidate'))
      .finally(() => setLoading(false))
  }, [candidateId])

  async function handleDelete() {
    if (!candidate || !confirm(`Delete "${candidate.name}"? This cannot be undone.`)) return
    try {
      await api.deleteCandidate(candidate.id)
      navigate('/candidates')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete candidate')
    }
  }

  function handleShare() {
    copyText(window.location.href)
    shareFlash.flash()
  }

  if (loading && !candidate) {
    return (
      <div className="page">
        <p className="subtle">Loading…</p>
      </div>
    )
  }

  if (!candidate) {
    return (
      <div className="page">
        {error && <div className="error-banner">{error}</div>}
      </div>
    )
  }

  return (
    <div className="page candidate-details">
      <div className="candidate-toolbar">
        <Link to="/candidates" className="link-button">
          Close
        </Link>
        <div className="save-control">
          <button type="button" className="button-secondary" onClick={handleShare}>
            Share
          </button>
          {shareFlash.saved && <span className="save-confirmation">✓ Link copied</span>}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Keyed on candidate id so switching candidates remounts every section
          fresh instead of carrying over stale local state (active tab, form
          drafts, etc.) from whoever was open before. */}
      <div key={candidate.id}>
        <CandidateInfoCard candidate={candidate} onCandidateChange={setCandidate} onError={setError} />
        <StageTabs candidate={candidate} onCandidateChange={setCandidate} onError={setError} />
        <DocumentChecklist candidateId={candidate.id} candidateName={candidate.name} onError={setError} />
        <ScreeningAnswers candidate={candidate} onCandidateChange={setCandidate} onError={setError} />

        <button className="link-button danger" onClick={handleDelete}>
          Delete candidate
        </button>
      </div>
    </div>
  )
}

import { useCandidateAuth } from '../../candidateAuth/CandidateAuthContext'

/** Where a candidate lands right after registering/logging in. Deliberately
 * bare for now — browsing open jobs, applying, and tracking application
 * status are the next pieces of the candidate-facing side, not built yet. */
export function CandidateHomePage() {
  const { candidate } = useCandidateAuth()

  return (
    <div className="page">
      <div className="page-header">
        <h1>Welcome{candidate ? `, ${candidate.first_name}` : ''}</h1>
      </div>
      <div className="card section">
        <p>Your candidate account is set up.</p>
        <p className="subtle">
          Browsing open jobs and applying isn't built yet — that's the next piece of this portal.
          Check back soon.
        </p>
      </div>
    </div>
  )
}

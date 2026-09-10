import { useState } from 'react'
import { api, ApiError } from '../../api/client'
import { useSavedFlash } from '../../hooks/useSavedFlash'
import type { CandidateDetail } from '../../api/types'

interface AdditionalInfoProps {
  candidate: CandidateDetail
  onCandidateChange: (candidate: CandidateDetail) => void
  onError: (message: string) => void
}

// null (never answered / manually-created candidate) <-> '', otherwise yes/no.
function toSelectValue(v: boolean | null): '' | 'yes' | 'no' {
  if (v === null) return ''
  return v ? 'yes' : 'no'
}

function fromSelectValue(v: string): boolean | null {
  if (v === 'yes') return true
  if (v === 'no') return false
  return null
}

/** The two work-eligibility questions the public apply form collects
 * (routes/apply.py) but which had no recruiter-facing surface until now -
 * shown here, editable, right under the pre-screening answers. */
export function AdditionalInfo({ candidate, onCandidateChange, onError }: AdditionalInfoProps) {
  const [workAuthorized, setWorkAuthorized] = useState(toSelectValue(candidate.work_authorized))
  const [requiresVisa, setRequiresVisa] = useState(toSelectValue(candidate.requires_visa_sponsorship))
  const [saving, setSaving] = useState(false)
  const saved = useSavedFlash()

  const dirty =
    fromSelectValue(workAuthorized) !== candidate.work_authorized ||
    fromSelectValue(requiresVisa) !== candidate.requires_visa_sponsorship

  async function handleSave() {
    setSaving(true)
    try {
      onCandidateChange(
        await api.updateCandidate(candidate.id, {
          work_authorized: fromSelectValue(workAuthorized),
          requires_visa_sponsorship: fromSelectValue(requiresVisa),
        }),
      )
      saved.flash()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card section">
      <div className="section-header">
        <h2>Additional information</h2>
        <div className="save-control">
          <button type="button" onClick={handleSave} disabled={saving || !dirty}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          {saved.saved && <span className="save-confirmation">✓ Saved</span>}
        </div>
      </div>
      <div className="form-row">
        <label>
          Legally authorized to work in the US
          <select value={workAuthorized} onChange={(e) => setWorkAuthorized(e.target.value as '' | 'yes' | 'no')}>
            <option value="">Not provided</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label>
          Requires visa sponsorship
          <select value={requiresVisa} onChange={(e) => setRequiresVisa(e.target.value as '' | 'yes' | 'no')}>
            <option value="">Not provided</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
      </div>
    </div>
  )
}

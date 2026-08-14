import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { MeetingStageTemplate, MeetingType } from '../api/types'
import { useJobDetailContext } from './JobDetailLayout'

const MEETING_TYPES: MeetingType[] = ['Interview', 'Orientation', 'Other']

export function JobMeetingStagesPage() {
  const { job } = useJobDetailContext()
  const [templates, setTemplates] = useState<MeetingStageTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [meetingType, setMeetingType] = useState<MeetingType | ''>('')
  const [stageName, setStageName] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listMeetingStages(job.id)
      setTemplates(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load meeting stages')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id])

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (!meetingType || !stageName) return
    setSubmitting(true)
    setError(null)
    try {
      await api.createMeetingStage(job.id, { meeting_type: meetingType, stage_name: stageName })
      setMeetingType('')
      setStageName('')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to add meeting stage')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(template: MeetingStageTemplate) {
    try {
      await api.deleteMeetingStage(job.id, template.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove meeting stage')
    }
  }

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}

      <div className="card section">
        <div className="section-header">
          <h2>Meeting stages</h2>
        </div>
        <p className="subtle">
          The stages a candidate for this job goes through, e.g. an interview stage named after the
          role, followed by an orientation stage.
        </p>

        {loading ? (
          <p className="subtle">Loading…</p>
        ) : templates.length === 0 ? (
          <p className="subtle">No meeting stages configured yet.</p>
        ) : (
          <ul className="enrolled-list">
            {templates.map((t) => (
              <li key={t.id}>
                <span>
                  <span className="chip">{t.meeting_type}</span> {t.stage_name}
                </span>
                <button className="link-button danger" onClick={() => handleRemove(t)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        <form className="form-row enroll-add" onSubmit={handleAdd} style={{ marginTop: '1rem' }}>
          <select value={meetingType} onChange={(e) => setMeetingType(e.target.value as MeetingType)}>
            <option value="">Meeting type…</option>
            {MEETING_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={stageName}
            onChange={(e) => setStageName(e.target.value)}
            placeholder="Stage name, e.g. CHHA"
          />
          <button type="submit" disabled={submitting || !meetingType || !stageName}>
            {submitting ? 'Adding…' : 'Add stage'}
          </button>
        </form>
      </div>
    </div>
  )
}

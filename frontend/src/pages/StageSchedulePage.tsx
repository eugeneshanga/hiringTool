import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import type { Candidate, Interview, MeetingType, StageMeetingType } from '../api/types'
import { useStageEditorContext } from './StageEditorLayout'

// Interview.meeting_type still uses the older, narrower vocabulary than
// MeetingStageTemplate.meeting_type — map into it when scheduling a session
// for a stage, since there's no exact one-to-one equivalent.
function toInterviewMeetingType(type: StageMeetingType): MeetingType {
  switch (type) {
    case 'In-person orientation':
      return 'Orientation'
    case 'Instant meeting link':
      return 'Other'
    default:
      return 'Interview'
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatTimeRange(startIso: string, endIso: string) {
  const start = new Date(startIso)
  const end = new Date(endIso)
  const fmt = (d: Date) => d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  const hours = (end.getTime() - start.getTime()) / (1000 * 60 * 60)
  const hoursLabel = Number.isInteger(hours) ? `${hours}h` : `${hours.toFixed(1)}h`
  return `${fmt(start)} - ${fmt(end)} (${hoursLabel})`
}

function toLocalDateValue(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function StageSchedulePage() {
  const { job, template } = useStageEditorContext()

  const [sessions, setSessions] = useState<Interview[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [enrollSelection, setEnrollSelection] = useState<Record<number, string>>({})

  const [showAddSession, setShowAddSession] = useState(false)
  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('10:00')
  const [location, setLocation] = useState('')
  const [capacity, setCapacity] = useState(1)
  const [submittingSession, setSubmittingSession] = useState(false)

  async function loadSessions() {
    setLoadingSessions(true)
    setError(null)
    try {
      const [interviewData, candidateData] = await Promise.all([
        api.listInterviews({ job_id: job.id }),
        api.listCandidates(),
      ])
      setSessions(interviewData)
      setCandidates(candidateData)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load sessions')
    } finally {
      setLoadingSessions(false)
    }
  }

  useEffect(() => {
    loadSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, template.id])

  const stageSessions = sessions
    .filter((s) => s.stage_name === template.stage_name)
    .sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start))

  function openAddSession() {
    setDate(toLocalDateValue(new Date()))
    setStartTime('09:00')
    setEndTime('10:00')
    setLocation('')
    setCapacity(1)
    setShowAddSession(true)
  }

  async function handleAddSession(e: FormEvent) {
    e.preventDefault()
    if (!date) return
    setSubmittingSession(true)
    setError(null)
    try {
      await api.createInterview({
        job_id: job.id,
        stage_name: template.stage_name,
        meeting_type: toInterviewMeetingType(template.meeting_type),
        scheduled_start: new Date(`${date}T${startTime}`).toISOString(),
        scheduled_end: new Date(`${date}T${endTime}`).toISOString(),
        location: location || null,
        capacity,
      })
      setShowAddSession(false)
      await loadSessions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to add session')
    } finally {
      setSubmittingSession(false)
    }
  }

  async function handleDeleteSession(session: Interview) {
    if (!confirm(`Delete the session on ${formatDate(session.scheduled_start)}?`)) return
    try {
      await api.deleteInterview(session.id)
      await loadSessions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete session')
    }
  }

  async function handleEnroll(session: Interview) {
    const candidateId = Number(enrollSelection[session.id])
    if (!candidateId) return
    try {
      await api.enrollCandidate(session.id, candidateId)
      setEnrollSelection((prev) => ({ ...prev, [session.id]: '' }))
      await loadSessions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to enroll candidate')
    }
  }

  async function handleUnenroll(session: Interview, candidateId: number) {
    try {
      await api.unenrollCandidate(session.id, candidateId)
      await loadSessions()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove candidate')
    }
  }

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}

      <div className="card section">
        <div className="section-header">
          <h2>Sessions</h2>
          <button type="button" onClick={openAddSession}>
            Add session
          </button>
        </div>

        {loadingSessions ? (
          <p className="subtle">Loading…</p>
        ) : stageSessions.length === 0 ? (
          <p className="subtle">No sessions scheduled for this stage yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Time</th>
                <th>Scheduled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {stageSessions.map((session) => {
                const enrolledIds = new Set(session.candidates.map((c) => c.id))
                const availableCandidates = candidates.filter((c) => !enrolledIds.has(c.id))
                const isExpanded = expandedId === session.id
                return (
                  <Fragment key={session.id}>
                    <tr>
                      <td>{formatDate(session.scheduled_start)}</td>
                      <td>{formatTimeRange(session.scheduled_start, session.scheduled_end)}</td>
                      <td>
                        <button
                          className="link-button"
                          onClick={() => setExpandedId(isExpanded ? null : session.id)}
                        >
                          {session.scheduled_count}/{session.capacity}
                        </button>
                      </td>
                      <td>
                        <button className="link-button danger" onClick={() => handleDeleteSession(session)}>
                          Delete
                        </button>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="detail-row">
                        <td colSpan={4}>
                          <div className="enroll-panel">
                            {session.candidates.length > 0 ? (
                              <ul className="enrolled-list">
                                {session.candidates.map((c) => (
                                  <li key={c.id}>
                                    {c.name}
                                    <button
                                      className="link-button danger"
                                      onClick={() => handleUnenroll(session, c.id)}
                                    >
                                      Remove
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="subtle">No candidates enrolled yet.</p>
                            )}
                            {session.scheduled_count < session.capacity && (
                              <div className="enroll-add">
                                <select
                                  value={enrollSelection[session.id] ?? ''}
                                  onChange={(e) =>
                                    setEnrollSelection((prev) => ({ ...prev, [session.id]: e.target.value }))
                                  }
                                >
                                  <option value="">Select a candidate…</option>
                                  {availableCandidates.map((c) => (
                                    <option key={c.id} value={c.id}>
                                      {c.name}
                                    </option>
                                  ))}
                                </select>
                                <button onClick={() => handleEnroll(session)}>Enroll</button>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {showAddSession && (
        <Modal title="Add session" onClose={() => setShowAddSession(false)}>
          <form onSubmit={handleAddSession} className="form">
            <div className="form-row">
              <label>
                Date
                <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
              </label>
              <label>
                Start time
                <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} required />
              </label>
              <label>
                End time
                <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} required />
              </label>
            </div>
            <div className="form-row">
              <label>
                Capacity
                <input
                  type="number"
                  min={1}
                  value={capacity}
                  onChange={(e) => setCapacity(Number(e.target.value))}
                  required
                />
              </label>
              <label>
                Location / link
                <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Optional" />
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setShowAddSession(false)}>
                Cancel
              </button>
              <button type="submit" disabled={submittingSession}>
                {submittingSession ? 'Adding…' : 'Add'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

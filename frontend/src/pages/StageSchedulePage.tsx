import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import { needsCapacity, needsDuration, toInterviewMeetingType } from '../lib/meetingStageTypes'
import type { Candidate, Interview, Interviewer } from '../api/types'
import { useStageEditorContext } from './StageEditorLayout'

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
  const { job, template, onTemplateChange, sessionsVersion } = useStageEditorContext()

  const [durationInput, setDurationInput] = useState(template.duration_minutes?.toString() ?? '')
  const [windowInput, setWindowInput] = useState(String(template.scheduling_window_days))
  const [capacityInput, setCapacityInput] = useState(template.default_capacity?.toString() ?? '')
  const [interviewerInput, setInterviewerInput] = useState(template.interviewer_user_id?.toString() ?? '')
  const [interviewers, setInterviewers] = useState<Interviewer[]>([])
  const [savingSettings, setSavingSettings] = useState(false)

  // Who can be assigned to check their calendar for this stage's public
  // apply-flow availability (see google_calendar.py) - any active user, not
  // just admins (GET /api/organization/interviewers is deliberately not
  // admin-gated, unlike the full user list).
  useEffect(() => {
    api.listInterviewers().then(setInterviewers).catch(() => {
      // Non-critical - the picker just shows no options if this fails.
    })
  }, [])

  const [sessions, setSessions] = useState<Interview[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [enrollSelection, setEnrollSelection] = useState<Record<number, string>>({})
  const [showFilter, setShowFilter] = useState<'upcoming' | 'past'>('upcoming')
  const [dateSortDir, setDateSortDir] = useState<'asc' | 'desc'>('asc')

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
    // sessionsVersion bumps after scheduling a session from the "Schedule
    // interview" button in the header, so this list stays in sync with it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, template.id, sessionsVersion])

  async function handleSaveSettings() {
    setSavingSettings(true)
    setError(null)
    try {
      const updated = await api.updateMeetingStage(job.id, template.id, {
        duration_minutes: needsDuration(template.meeting_type) && durationInput ? Number(durationInput) : null,
        scheduling_window_days: Number(windowInput) || 0,
        default_capacity: needsCapacity(template.meeting_type) && capacityInput ? Number(capacityInput) : null,
        interviewer_user_id: needsDuration(template.meeting_type) && interviewerInput ? Number(interviewerInput) : null,
      })
      onTemplateChange(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save settings')
    } finally {
      setSavingSettings(false)
    }
  }

  // Separate from handleSaveSettings (which reads the other fields' *state*,
  // updated on their own onChange/onBlur cycle) because a <select>'s
  // onChange fires before the setInterviewerInput state update has been
  // applied - routing through handleSaveSettings here would PATCH with the
  // stale previous value. Sends interviewer_user_id alone; the PATCH
  // endpoint only touches fields present in the body.
  async function handleInterviewerChange(value: string) {
    setInterviewerInput(value)
    setSavingSettings(true)
    setError(null)
    try {
      const updated = await api.updateMeetingStage(job.id, template.id, {
        interviewer_user_id: value ? Number(value) : null,
      })
      onTemplateChange(updated)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save interviewer')
    } finally {
      setSavingSettings(false)
    }
  }

  // Prefer the real FK; fall back to a stage_name match only for sessions
  // created before it existed (or ad-hoc ones with no template at all).
  const stageSessions = sessions.filter(
    (s) =>
      s.meeting_stage_template_id === template.id ||
      (s.meeting_stage_template_id == null && s.stage_name === template.stage_name),
  )

  // "Show" filter + Date-column sort are both client-side over the sessions
  // already loaded above - no separate API call for either.
  const now = new Date().toISOString()
  const visibleSessions = stageSessions
    .filter((s) => (showFilter === 'upcoming' ? s.scheduled_start >= now : s.scheduled_start < now))
    .sort((a, b) =>
      dateSortDir === 'asc'
        ? a.scheduled_start.localeCompare(b.scheduled_start)
        : b.scheduled_start.localeCompare(a.scheduled_start),
    )

  function toggleDateSort() {
    setDateSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))
  }

  function openAddSession() {
    setDate(toLocalDateValue(new Date()))
    setStartTime('09:00')
    setEndTime('10:00')
    // Pre-fill from the stage's own defaults (set in "Create new meeting
    // stage" / editable there today) - just a starting point, not enforced;
    // this session can still be edited to something else before saving.
    setLocation(template.location ?? '')
    setCapacity(template.default_capacity ?? 1)
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
        meeting_stage_template_id: template.id,
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

      <div className="card stage-settings-box">
        {needsDuration(template.meeting_type) && (
          <label>
            Interview length (minutes)
            <input
              type="number"
              min={1}
              value={durationInput}
              onChange={(e) => setDurationInput(e.target.value)}
              onBlur={handleSaveSettings}
            />
          </label>
        )}
        {needsDuration(template.meeting_type) && (
          <label>
            Interviewer (public apply calendar)
            <select value={interviewerInput} onChange={(e) => handleInterviewerChange(e.target.value)}>
              <option value="">Not assigned</option>
              {interviewers.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Days in advance to allow scheduling
          <input
            type="number"
            min={0}
            value={windowInput}
            onChange={(e) => setWindowInput(e.target.value)}
            onBlur={handleSaveSettings}
          />
        </label>
        {needsCapacity(template.meeting_type) && (
          <label>
            Max candidates per session
            <input
              type="number"
              min={1}
              value={capacityInput}
              onChange={(e) => setCapacityInput(e.target.value)}
              onBlur={handleSaveSettings}
            />
          </label>
        )}
        {savingSettings && <span className="subtle">Saving…</span>}
      </div>

      <div className="card section">
        <div className="section-header">
          <h2>Sessions</h2>
          <button type="button" onClick={openAddSession}>
            Add session
          </button>
        </div>

        <div className="sessions-show-row">
          <label className="sessions-show-label">
            Show
            <select value={showFilter} onChange={(e) => setShowFilter(e.target.value as 'upcoming' | 'past')}>
              <option value="upcoming">Upcoming</option>
              <option value="past">Past</option>
            </select>
          </label>
        </div>

        {loadingSessions ? (
          <p className="subtle">Loading…</p>
        ) : visibleSessions.length === 0 ? (
          <p className="subtle">
            {showFilter === 'upcoming' ? 'No upcoming sessions for this stage.' : 'No past sessions for this stage.'}
          </p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>
                  <button type="button" className="sort-header" onClick={toggleDateSort}>
                    Date
                    <span className="sort-arrow">{dateSortDir === 'asc' ? '↑' : '↓'}</span>
                  </button>
                </th>
                <th>Time</th>
                <th>Scheduled</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visibleSessions.map((session) => {
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

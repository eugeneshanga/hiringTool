import { Fragment, useEffect, useMemo, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { Candidate, Interview, Job } from '../api/types'

const timeZoneLabel = Intl.DateTimeFormat().resolvedOptions().timeZone

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

function toLocalInputValue(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function HomePage() {
  const [interviews, setInterviews] = useState<Interview[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [typeFilter, setTypeFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [enrollSelection, setEnrollSelection] = useState<Record<number, string>>({})

  const [stageName, setStageName] = useState('')
  const [meetingType, setMeetingType] = useState('')
  const [jobId, setJobId] = useState('')
  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('10:00')
  const [location, setLocation] = useState('')
  const [capacity, setCapacity] = useState(1)
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [interviewData, jobData, candidateData] = await Promise.all([
        api.listInterviews({ upcoming: true }),
        api.listJobs(),
        api.listCandidates(),
      ])
      setInterviews(interviewData)
      setJobs(jobData)
      setCandidates(candidateData)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load upcoming interviews')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const meetingTypes = useMemo(
    () => Array.from(new Set(interviews.map((i) => i.meeting_type))).sort(),
    [interviews],
  )

  const visibleInterviews = useMemo(
    () => (typeFilter ? interviews.filter((i) => i.meeting_type === typeFilter) : interviews),
    [interviews, typeFilter],
  )

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (!date) return
    setSubmitting(true)
    setError(null)
    try {
      const scheduled_start = new Date(`${date}T${startTime}`).toISOString()
      const scheduled_end = new Date(`${date}T${endTime}`).toISOString()
      await api.createInterview({
        stage_name: stageName,
        meeting_type: meetingType,
        job_id: jobId ? Number(jobId) : null,
        scheduled_start,
        scheduled_end,
        location: location || null,
        capacity,
      })
      setStageName('')
      setMeetingType('')
      setJobId('')
      setDate('')
      setLocation('')
      setCapacity(1)
      setShowForm(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create interview')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleEnroll(interview: Interview) {
    const candidateId = Number(enrollSelection[interview.id])
    if (!candidateId) return
    try {
      await api.enrollCandidate(interview.id, candidateId)
      setEnrollSelection((prev) => ({ ...prev, [interview.id]: '' }))
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to enroll candidate')
    }
  }

  async function handleUnenroll(interview: Interview, candidateId: number) {
    try {
      await api.unenrollCandidate(interview.id, candidateId)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove candidate')
    }
  }

  async function handleDelete(interview: Interview) {
    if (!confirm(`Delete "${interview.stage_name}" on ${formatDate(interview.scheduled_start)}?`)) return
    try {
      await api.deleteInterview(interview.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete interview')
    }
  }

  const enrolledIdsFor = (interview: Interview) => new Set(interview.candidates.map((c) => c.id))

  return (
    <div className="page">
      <div className="page-header">
        <h1>Upcoming</h1>
        <div className="page-header-actions">
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="">All</option>
            {meetingTypes.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <button
            onClick={() => {
              setShowForm((v) => !v)
              if (!date) setDate(toLocalInputValue(new Date()))
            }}
          >
            {showForm ? 'Cancel' : 'New interview'}
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showForm && (
        <form className="card form" onSubmit={handleCreate}>
          <div className="form-row">
            <label>
              Meeting stage name
              <input
                value={stageName}
                onChange={(e) => setStageName(e.target.value)}
                placeholder="Orientation"
                required
              />
            </label>
            <label>
              Meeting type
              <input
                value={meetingType}
                onChange={(e) => setMeetingType(e.target.value)}
                placeholder="In-person orientation"
                required
              />
            </label>
            <label>
              Job (optional)
              <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
                <option value="">Not job-specific</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="form-row">
            <label>
              Date
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
            </label>
            <label>
              Start time
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                required
              />
            </label>
            <label>
              End time
              <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} required />
            </label>
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
          </div>
          <label>
            Location / link
            <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Optional" />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? 'Scheduling…' : 'Schedule interview'}
          </button>
        </form>
      )}

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : visibleInterviews.length === 0 ? (
        <p className="subtle">Nothing upcoming.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Time - {timeZoneLabel}</th>
              <th>Meeting stage name</th>
              <th>Meeting type</th>
              <th>Scheduled</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visibleInterviews.map((interview) => {
              const enrolledIds = enrolledIdsFor(interview)
              const availableCandidates = candidates.filter((c) => !enrolledIds.has(c.id))
              const isExpanded = expandedId === interview.id
              return (
                <Fragment key={interview.id}>
                  <tr>
                    <td>{formatDate(interview.scheduled_start)}</td>
                    <td>{formatTimeRange(interview.scheduled_start, interview.scheduled_end)}</td>
                    <td>
                      <strong>{interview.stage_name}</strong>
                      {interview.job_title && <div className="subtle">{interview.job_title}</div>}
                    </td>
                    <td>{interview.meeting_type}</td>
                    <td>
                      <button
                        className="link-button"
                        onClick={() => setExpandedId(isExpanded ? null : interview.id)}
                      >
                        {interview.scheduled_count}/{interview.capacity}
                      </button>
                    </td>
                    <td>
                      <button className="link-button danger" onClick={() => handleDelete(interview)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="detail-row">
                      <td colSpan={6}>
                        <div className="enroll-panel">
                          {interview.candidates.length > 0 ? (
                            <ul className="enrolled-list">
                              {interview.candidates.map((c) => (
                                <li key={c.id}>
                                  {c.name}
                                  <button
                                    className="link-button danger"
                                    onClick={() => handleUnenroll(interview, c.id)}
                                  >
                                    Remove
                                  </button>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="subtle">No candidates enrolled yet.</p>
                          )}
                          {interview.scheduled_count < interview.capacity && (
                            <div className="enroll-add">
                              <select
                                value={enrollSelection[interview.id] ?? ''}
                                onChange={(e) =>
                                  setEnrollSelection((prev) => ({ ...prev, [interview.id]: e.target.value }))
                                }
                              >
                                <option value="">Select a candidate…</option>
                                {availableCandidates.map((c) => (
                                  <option key={c.id} value={c.id}>
                                    {c.name}
                                  </option>
                                ))}
                              </select>
                              <button onClick={() => handleEnroll(interview)}>Enroll</button>
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
  )
}

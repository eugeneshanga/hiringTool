import { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import { toInterviewMeetingType } from '../lib/meetingStageTypes'
import type { Candidate, Interview, Job, MeetingStageTemplate } from '../api/types'

type CandidateMode = 'search' | 'manual'
type SlotMode = 'available' | 'custom'

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function dateKey(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function startOfMonth(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

/** 42 cells (6 full weeks) covering the given month, starting on the Sunday
 * on or before the 1st — enough to render a standard month grid. */
function buildCalendarCells(month: Date) {
  const first = startOfMonth(month)
  const start = new Date(first)
  start.setDate(start.getDate() - first.getDay())
  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(start)
    date.setDate(start.getDate() + i)
    return date
  })
}

function isSameDay(a: Date, b: Date) {
  return dateKey(a) === dateKey(b)
}

interface ScheduleInterviewModalProps {
  job: Job
  template: MeetingStageTemplate
  onClose: () => void
  onScheduled: () => void
}

/** "Schedule interview" from the Stage editor header: pick or create a
 * candidate, then either drop them into an existing open session for this
 * stage (picked from a small calendar) or spin up a brand-new one-off slot. */
export function ScheduleInterviewModal({ job, template, onClose, onScheduled }: ScheduleInterviewModalProps) {
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const [candidateMode, setCandidateMode] = useState<CandidateMode>('search')
  const [candidateSearch, setCandidateSearch] = useState('')
  const [candidateResults, setCandidateResults] = useState<Candidate[]>([])
  const [searchingCandidates, setSearchingCandidates] = useState(false)
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)
  const [manualName, setManualName] = useState('')
  const [manualEmail, setManualEmail] = useState('')
  const [manualPhone, setManualPhone] = useState('')

  const [slotMode, setSlotMode] = useState<SlotMode>('available')
  const [sessions, setSessions] = useState<Interview[]>([])
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [calendarMonth, setCalendarMonth] = useState(() => startOfMonth(new Date()))
  const [selectedDate, setSelectedDate] = useState<Date | null>(() => new Date())
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null)

  const [customDate, setCustomDate] = useState('')
  const [customStartTime, setCustomStartTime] = useState('09:00')
  const [customEndTime, setCustomEndTime] = useState('10:00')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoadingSessions(true)
      try {
        const data = await api.listInterviews({ job_id: job.id })
        if (!cancelled) setSessions(data)
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Failed to load sessions')
      } finally {
        if (!cancelled) setLoadingSessions(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [job.id])

  useEffect(() => {
    if (candidateMode !== 'search' || candidateSearch.trim().length < 3) {
      setCandidateResults([])
      return
    }
    let cancelled = false
    setSearchingCandidates(true)
    const timeout = setTimeout(async () => {
      try {
        const results = await api.listCandidates({ search: candidateSearch.trim() })
        if (!cancelled) setCandidateResults(results)
      } catch {
        // search is a convenience — a transient failure here isn't worth surfacing
      } finally {
        if (!cancelled) setSearchingCandidates(false)
      }
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(timeout)
    }
  }, [candidateSearch, candidateMode])

  // Prefer the real FK; fall back to a stage_name match for sessions created
  // before it existed — same rule StageSchedulePage uses.
  const openStageSessions = useMemo(
    () =>
      sessions.filter(
        (s) =>
          (s.meeting_stage_template_id === template.id ||
            (s.meeting_stage_template_id == null && s.stage_name === template.stage_name)) &&
          s.scheduled_count < s.capacity &&
          new Date(s.scheduled_start) >= new Date(),
      ),
    [sessions, template],
  )

  const sessionsByDate = useMemo(() => {
    const map = new Map<string, Interview[]>()
    for (const session of openStageSessions) {
      const key = dateKey(new Date(session.scheduled_start))
      const existing = map.get(key)
      if (existing) existing.push(session)
      else map.set(key, [session])
    }
    return map
  }, [openStageSessions])

  const selectedDateSessions = selectedDate ? sessionsByDate.get(dateKey(selectedDate)) ?? [] : []
  const monthLabel = calendarMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  const today = new Date()

  function changeMonth(delta: number) {
    setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1))
  }

  const candidateIsValid =
    candidateMode === 'search' ? selectedCandidate != null : manualName.trim() !== '' && manualEmail.trim() !== ''
  const slotIsValid =
    slotMode === 'available'
      ? selectedSessionId != null
      : customDate !== '' && customStartTime !== '' && customEndTime !== ''
  const canSave = candidateIsValid && slotIsValid && !submitting

  async function handleSave() {
    if (!canSave) return
    setSubmitting(true)
    setError(null)
    try {
      let candidateId: number
      if (candidateMode === 'search') {
        candidateId = selectedCandidate!.id
      } else {
        const created = await api.createCandidate({
          name: manualName.trim(),
          email: manualEmail.trim(),
          phone: manualPhone.trim() || null,
          job_id: job.id,
        })
        candidateId = created.id
      }

      let interviewId: number
      if (slotMode === 'available') {
        interviewId = selectedSessionId!
      } else {
        const created = await api.createInterview({
          job_id: job.id,
          meeting_stage_template_id: template.id,
          stage_name: template.stage_name,
          meeting_type: toInterviewMeetingType(template.meeting_type),
          scheduled_start: new Date(`${customDate}T${customStartTime}`).toISOString(),
          scheduled_end: new Date(`${customDate}T${customEndTime}`).toISOString(),
          capacity: 1,
        })
        interviewId = created.id
      }

      await api.enrollCandidate(interviewId, candidateId)
      onScheduled()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to schedule interview')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal title="Schedule" onClose={onClose} size="wide">
      <div className="form">
        {error && <div className="error-banner">{error}</div>}

        <div className="radio-list">
          <label className="radio-option">
            <input
              type="radio"
              name="candidate-mode"
              checked={candidateMode === 'search'}
              onChange={() => setCandidateMode('search')}
            />
            Search existing candidate
          </label>
          <label className="radio-option">
            <input
              type="radio"
              name="candidate-mode"
              checked={candidateMode === 'manual'}
              onChange={() => setCandidateMode('manual')}
            />
            Enter candidate details manually
          </label>
        </div>

        {candidateMode === 'search' ? (
          <label>
            Search candidate by name/email:
            <input
              value={candidateSearch}
              onChange={(e) => {
                setCandidateSearch(e.target.value)
                setSelectedCandidate(null)
              }}
              placeholder="Type at least 3 characters to search"
            />
            {selectedCandidate ? (
              <p className="subtle">Selected: {selectedCandidate.name} ({selectedCandidate.email})</p>
            ) : searchingCandidates ? (
              <p className="subtle">Searching…</p>
            ) : candidateResults.length > 0 ? (
              <ul className="candidate-search-results">
                {candidateResults.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        setSelectedCandidate(c)
                        setCandidateSearch(c.name)
                        setCandidateResults([])
                      }}
                    >
                      {c.name} — {c.email}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </label>
        ) : (
          <div className="form-row">
            <label>
              Name
              <input value={manualName} onChange={(e) => setManualName(e.target.value)} required />
            </label>
            <label>
              Email
              <input type="email" value={manualEmail} onChange={(e) => setManualEmail(e.target.value)} required />
            </label>
            <label>
              Phone
              <input value={manualPhone} onChange={(e) => setManualPhone(e.target.value)} />
            </label>
          </div>
        )}

        <div className="radio-list">
          <label className="radio-option">
            <input
              type="radio"
              name="slot-mode"
              checked={slotMode === 'available'}
              onChange={() => setSlotMode('available')}
            />
            Available time slot
          </label>
          <label className="radio-option">
            <input
              type="radio"
              name="slot-mode"
              checked={slotMode === 'custom'}
              onChange={() => setSlotMode('custom')}
            />
            Custom time slot
          </label>
        </div>

        {slotMode === 'available' ? (
          <>
            <p className="subtle">
              These times reflect existing sessions for this stage that still have room.
            </p>
            {loadingSessions ? (
              <p className="subtle">Loading…</p>
            ) : (
              <div className="schedule-calendar-row">
                <div className="calendar">
                  <div className="calendar-header">
                    <strong>{monthLabel}</strong>
                    <div className="calendar-nav">
                      <button type="button" className="icon-button" onClick={() => changeMonth(-1)} aria-label="Previous month">
                        ‹
                      </button>
                      <button type="button" className="icon-button" onClick={() => changeMonth(1)} aria-label="Next month">
                        ›
                      </button>
                    </div>
                  </div>
                  <div className="calendar-grid">
                    {['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'].map((d) => (
                      <div key={d} className="calendar-weekday">
                        {d}
                      </div>
                    ))}
                    {buildCalendarCells(calendarMonth).map((day) => {
                      const inMonth = day.getMonth() === calendarMonth.getMonth()
                      const hasSessions = sessionsByDate.has(dateKey(day))
                      const isSelected = selectedDate != null && isSameDay(day, selectedDate)
                      const isToday = isSameDay(day, today)
                      return (
                        <button
                          key={day.toISOString()}
                          type="button"
                          className={`calendar-day${isSelected ? ' selected' : ''}${!inMonth ? ' outside-month' : ''}${isToday ? ' today' : ''}`}
                          onClick={() => {
                            setSelectedDate(day)
                            setSelectedSessionId(null)
                          }}
                        >
                          {day.getDate()}
                          {hasSessions && <span className="calendar-dot" />}
                        </button>
                      )
                    })}
                  </div>
                </div>
                <div className="calendar-day-panel">
                  {selectedDate && (
                    <p className="calendar-day-title">
                      {selectedDate.toLocaleDateString(undefined, {
                        weekday: 'long',
                        month: 'long',
                        day: 'numeric',
                        year: 'numeric',
                      })}
                    </p>
                  )}
                  {selectedDateSessions.length === 0 ? (
                    <p className="subtle">No available times on this date.</p>
                  ) : (
                    selectedDateSessions.map((session) => (
                      <button
                        key={session.id}
                        type="button"
                        className={`time-slot-button${selectedSessionId === session.id ? ' active' : ''}`}
                        onClick={() => setSelectedSessionId(session.id)}
                      >
                        {new Date(session.scheduled_start).toLocaleTimeString(undefined, {
                          hour: 'numeric',
                          minute: '2-digit',
                        })}
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="form-row">
            <label>
              Date
              <input type="date" value={customDate} onChange={(e) => setCustomDate(e.target.value)} required />
            </label>
            <label>
              Start time
              <input type="time" value={customStartTime} onChange={(e) => setCustomStartTime(e.target.value)} required />
            </label>
            <label>
              End time
              <input type="time" value={customEndTime} onChange={(e) => setCustomEndTime(e.target.value)} required />
            </label>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="button-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" onClick={handleSave} disabled={!canSave}>
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

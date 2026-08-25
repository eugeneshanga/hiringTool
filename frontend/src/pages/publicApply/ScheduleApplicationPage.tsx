import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { publicApplyApi, publicErrorMessage } from '../../api/publicApplyClient'
import { buildCalendarCells, dateKey, isSameDay, startOfMonth } from '../../lib/calendarGrid'
import type { BookingConfirmation, PublicApplication, PublicSlot } from '../../api/types'

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

function ClockIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
      <circle cx="8" cy="8" r="6.3" />
      <path d="M8 4.8V8l2.4 1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function MonitorIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
      <rect x="1.5" y="2.5" width="13" height="8.5" rx="1.2" />
      <path d="M5.5 13.5h5M8 11v2.5" strokeLinecap="round" />
    </svg>
  )
}

/** A booking's essentials — shared by "you already scheduled this" (GET, on
 * load) and "you just scheduled this" (the POST /submit response). */
function BookingSummary({
  jobTitle, stageName, scheduledStart, meetingLink, confirmationCode,
}: {
  jobTitle: string
  stageName: string | null
  scheduledStart: string | null
  meetingLink: string | null
  confirmationCode: string | null
}) {
  return (
    <div className="card public-card">
      <h1>You're all set!</h1>
      <p>
        {stageName ?? 'Your interview'} for {jobTitle}
        {scheduledStart && <> is scheduled for <strong>{formatDateTime(scheduledStart)}</strong></>}.
      </p>
      {meetingLink && (
        <p>
          Meeting link: <a href={meetingLink} target="_blank" rel="noreferrer">{meetingLink}</a>
        </p>
      )}
      {confirmationCode && (
        <p>
          Confirmation code: <strong>{confirmationCode}</strong>
        </p>
      )}
      {confirmationCode && (
        <p className="subtle">
          You can check back on this anytime at{' '}
          <Link to={`/status?code=${encodeURIComponent(confirmationCode)}`}>your status page</Link>.
        </p>
      )}
    </div>
  )
}

/** Step 2/3 of the public apply flow (no login) — the link emailed after
 * POST /api/apply. Loads that job's screening questions + open interview
 * slots (GET /api/apply/<token>) and submits both together atomically
 * (POST /api/apply/<token>/submit) — see routes/apply.py. The date/time
 * picker is the same month-grid-plus-day-panel calendar as the recruiter
 * side's ScheduleInterviewModal (see lib/calendarGrid.ts), just driven by
 * live Google Calendar availability instead of existing sessions. */
export function ScheduleApplicationPage() {
  const { token } = useParams<{ token: string }>()

  const [data, setData] = useState<PublicApplication | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [calendarMonth, setCalendarMonth] = useState(() => startOfMonth(new Date()))
  const [selectedDate, setSelectedDate] = useState<Date | null>(null)
  const [selectedSlot, setSelectedSlot] = useState<PublicSlot | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [booked, setBooked] = useState<BookingConfirmation | null>(null)
  // Jumps the calendar to the soonest available day exactly once, the first
  // time slots load - without this guard, re-running on every `data` update
  // (e.g. after a stale-slot refetch) would yank the recruiter's own month/
  // day navigation back to wherever the earliest slot happens to be.
  const hasInitializedCalendar = useRef(false)

  function load() {
    if (!token) return
    setLoading(true)
    setLoadError(null)
    publicApplyApi
      .getApplication(token)
      .then(setData)
      .catch((err) => setLoadError(publicErrorMessage(err, 'This link is invalid.')))
      .finally(() => setLoading(false))
  }

  useEffect(load, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  const openData = data && !data.already_scheduled ? data : null

  const slotsByDate = useMemo(() => {
    const map = new Map<string, PublicSlot[]>()
    for (const slot of openData?.available_slots ?? []) {
      const key = dateKey(new Date(slot.start))
      const existing = map.get(key)
      if (existing) existing.push(slot)
      else map.set(key, [slot])
    }
    return map
  }, [openData])

  useEffect(() => {
    if (hasInitializedCalendar.current || !openData) return
    const firstSlot = openData.available_slots[0]
    const initialDate = firstSlot ? new Date(firstSlot.start) : new Date()
    setSelectedDate(initialDate)
    setCalendarMonth(startOfMonth(initialDate))
    hasInitializedCalendar.current = true
  }, [openData])

  function changeMonth(delta: number) {
    setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!token || !selectedSlot) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      const result = await publicApplyApi.submitApplication(token, {
        answers: Object.entries(answers).map(([questionId, answerText]) => ({
          question_id: Number(questionId),
          answer_text: answerText,
        })),
        slot_start: selectedSlot.start,
        slot_end: selectedSlot.end,
      })
      setBooked(result)
    } catch (err) {
      setSubmitError(publicErrorMessage(err))
      // The chosen slot may have just been taken by someone else, or the
      // available list may otherwise be stale — refresh it rather than
      // leaving a now-possibly-invalid selection in place.
      setSelectedSlot(null)
      load()
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="page-loading">Loading…</div>

  if (loadError) {
    return (
      <div className="public-page">
        <div className="card public-card">
          <h1>HiringTool</h1>
          <p className="error-banner">{loadError}</p>
        </div>
      </div>
    )
  }

  if (booked && data) {
    return (
      <div className="public-page">
        <BookingSummary
          jobTitle={data.job_title}
          stageName={data.stage_name}
          scheduledStart={booked.scheduled_start}
          meetingLink={booked.meeting_link}
          confirmationCode={booked.confirmation_code}
        />
      </div>
    )
  }

  if (data?.already_scheduled) {
    return (
      <div className="public-page">
        <BookingSummary
          jobTitle={data.job_title}
          stageName={data.stage_name}
          scheduledStart={data.scheduled_start}
          meetingLink={data.meeting_link}
          confirmationCode={data.confirmation_code}
        />
      </div>
    )
  }

  if (!openData) return null

  const noSlotsAvailable = openData.available_slots.length === 0
  const canSubmit = selectedSlot != null && !submitting && !noSlotsAvailable
  const monthLabel = calendarMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  const today = new Date()
  const selectedDateSlots = selectedDate ? slotsByDate.get(dateKey(selectedDate)) ?? [] : []

  return (
    <div className="apply-page">
      <div className="apply-header">
        <h1>
          Schedule an interview{openData.job_title ? ` - ${openData.job_title}` : ''}
        </h1>
        <p className="schedule-org-name">{openData.organization_name}</p>
        <div className="schedule-meta">
          {openData.meeting_type && (
            <span className="schedule-meta-row">
              <MonitorIcon /> {openData.meeting_type}
            </span>
          )}
          {openData.duration_minutes != null && (
            <span className="schedule-meta-row">
              <ClockIcon /> {openData.duration_minutes} min
            </span>
          )}
        </div>
      </div>

      <form className="form" onSubmit={handleSubmit}>
        {openData.screening_questions.length > 0 && (
          <>
            <h2 className="apply-section-heading apply-section-heading-first">A few quick questions</h2>
            <div className="screening-list">
              {openData.screening_questions.map((q) => (
                <label key={q.id}>
                  {q.question_text}
                  {q.answer_options.length > 0 ? (
                    <select
                      value={answers[q.id] ?? ''}
                      onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                    >
                      <option value="">Select an answer…</option>
                      {q.answer_options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      value={answers[q.id] ?? ''}
                      onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                    />
                  )}
                </label>
              ))}
            </div>
          </>
        )}

        <h2 className={`apply-section-heading${openData.screening_questions.length === 0 ? ' apply-section-heading-first' : ''}`}>
          Select a date &amp; time
        </h2>

        {noSlotsAvailable ? (
          <p className="subtle">
            No times are available to book right now — we'll reach out directly to get you scheduled.
          </p>
        ) : (
          <div className="schedule-calendar-row">
            <div className="calendar">
              <p className="calendar-duration-label">
                <ClockIcon /> {openData.duration_minutes} minutes
              </p>
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
                  const hasSlots = slotsByDate.has(dateKey(day))
                  const isSelected = selectedDate != null && isSameDay(day, selectedDate)
                  const isToday = isSameDay(day, today)
                  return (
                    <button
                      key={day.toISOString()}
                      type="button"
                      className={`calendar-day${isSelected ? ' selected' : ''}${!inMonth ? ' outside-month' : ''}${isToday ? ' today' : ''}${hasSlots && !isSelected ? ' has-availability' : ''}`}
                      onClick={() => setSelectedDate(day)}
                    >
                      {day.getDate()}
                      {hasSlots && <span className="calendar-dot" />}
                    </button>
                  )
                })}
              </div>
            </div>
            <div className="calendar-day-panel">
              {selectedDate && (
                <p className="calendar-day-title">
                  {selectedDate.toLocaleDateString(undefined, {
                    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
                  })}
                </p>
              )}
              {selectedDateSlots.length === 0 ? (
                <p className="subtle">No available times on this date.</p>
              ) : (
                selectedDateSlots.map((slot) => (
                  <button
                    key={slot.start}
                    type="button"
                    className={`time-slot-button${selectedSlot?.start === slot.start ? ' active' : ''}`}
                    onClick={() => setSelectedSlot(slot)}
                  >
                    {formatTime(slot.start)}
                  </button>
                ))
              )}
            </div>
          </div>
        )}

        {submitError && <div className="error-banner">{submitError}</div>}
        <button type="submit" disabled={!canSubmit}>
          {submitting ? 'Booking…' : 'Confirm interview'}
        </button>
      </form>
    </div>
  )
}

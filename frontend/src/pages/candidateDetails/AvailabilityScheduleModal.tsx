import { useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../../api/client'
import { Modal } from '../../components/Modal'
import { buildCalendarCells, dateKey, isSameDay, startOfMonth } from '../../lib/calendarGrid'
import type { CandidateDetail, PublicSlot } from '../../api/types'

interface AvailabilityScheduleModalProps {
  candidateId: number
  templateId: number
  stageName: string
  durationMinutes: number | null
  onClose: () => void
  onScheduled: (candidate: CandidateDetail) => void
}

/** The month-grid-plus-day-panel calendar, driven by the assigned
 * interviewer's real Outlook availability - same component/data shape as
 * the candidate's own self-service booking (publicApply/
 * ScheduleApplicationPage.tsx), just fetched/booked through the
 * recruiter-authenticated equivalent (api.getAvailableSlots/bookStageSlot)
 * instead of a public token. Used for a stage that's been given a live
 * calendar (interviewer + duration - see StageTabs.tsx), whether that's an
 * interview's "Reschedule" or an orientation stage's "Schedule". */
export function AvailabilityScheduleModal({
  candidateId, templateId, stageName, durationMinutes, onClose, onScheduled,
}: AvailabilityScheduleModalProps) {
  const [slots, setSlots] = useState<PublicSlot[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const [calendarMonth, setCalendarMonth] = useState(() => startOfMonth(new Date()))
  const [selectedDate, setSelectedDate] = useState<Date | null>(null)
  const [selectedSlot, setSelectedSlot] = useState<PublicSlot | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const hasInitializedCalendar = useRef(false)

  function load() {
    setLoading(true)
    setLoadError(null)
    api
      .getAvailableSlots(candidateId, templateId)
      .then((data) => setSlots(data.available_slots))
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : 'Failed to load availability'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [candidateId, templateId]) // eslint-disable-line react-hooks/exhaustive-deps

  const slotsByDate = useMemo(() => {
    const map = new Map<string, PublicSlot[]>()
    for (const slot of slots ?? []) {
      const key = dateKey(new Date(slot.start))
      const existing = map.get(key)
      if (existing) existing.push(slot)
      else map.set(key, [slot])
    }
    return map
  }, [slots])

  useEffect(() => {
    if (hasInitializedCalendar.current || !slots) return
    const firstSlot = slots[0]
    const initialDate = firstSlot ? new Date(firstSlot.start) : new Date()
    setSelectedDate(initialDate)
    setCalendarMonth(startOfMonth(initialDate))
    hasInitializedCalendar.current = true
  }, [slots])

  function changeMonth(delta: number) {
    setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1))
  }

  async function handleConfirm() {
    if (!selectedSlot) return
    setSubmitError(null)
    setSubmitting(true)
    try {
      const updated = await api.bookStageSlot(candidateId, templateId, {
        slot_start: selectedSlot.start,
        slot_end: selectedSlot.end,
      })
      onScheduled(updated)
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Failed to book that slot')
      // The chosen slot may have just been taken (or the interviewer's
      // calendar changed) - refresh rather than leaving a stale selection.
      setSelectedSlot(null)
      load()
    } finally {
      setSubmitting(false)
    }
  }

  const monthLabel = calendarMonth.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  const today = new Date()
  const selectedDateSlots = selectedDate ? slotsByDate.get(dateKey(selectedDate)) ?? [] : []
  const noSlotsAvailable = slots != null && slots.length === 0

  return (
    <Modal title={`Schedule - ${stageName}`} onClose={onClose} size="wide">
      <div className="form">
        {loadError && <div className="error-banner">{loadError}</div>}
        {submitError && <div className="error-banner">{submitError}</div>}

        {loading ? (
          <p className="subtle">Loading availability…</p>
        ) : noSlotsAvailable ? (
          <p className="subtle">
            No times are available to book right now - the interviewer may not have a calendar connected, or has no
            open time in the current scheduling window.
          </p>
        ) : (
          <div className="schedule-calendar-row">
            <div className="calendar">
              {durationMinutes != null && <p className="calendar-duration-label">{durationMinutes} minutes</p>}
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
                    {new Date(slot.start).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
                  </button>
                ))
              )}
            </div>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="button-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" onClick={handleConfirm} disabled={!selectedSlot || submitting}>
            {submitting ? 'Booking…' : 'Confirm'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

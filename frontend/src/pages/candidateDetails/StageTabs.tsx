import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../../api/client'
import { Modal } from '../../components/Modal'
import { useSavedFlash } from '../../hooks/useSavedFlash'
import type { CandidateDetail, CandidateStage, StageProgressStatus } from '../../api/types'

const STAGE_STATUSES: StageProgressStatus[] = ['Upcoming', 'Completed', 'Cancelled', 'No show']

function formatDateTime(iso: string | null) {
  if (!iso) return null
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function toLocalDateValue(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function toLocalTimeValue(iso: string) {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function ScoreRow({
  label,
  value,
  onChange,
}: {
  label: string
  value: number | null
  onChange: (n: number) => void
}) {
  return (
    <div className="score-row">
      <div className="score-label">{label}</div>
      <div className="score-buttons">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={`score-button${value === n ? ' active' : ''}`}
            onClick={() => onChange(n)}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  )
}

interface StageTabsProps {
  candidate: CandidateDetail
  onCandidateChange: (candidate: CandidateDetail) => void
  onError: (message: string) => void
}

/** The per-meeting-stage tab strip: schedule/status, Cancel/Reschedule/Send
 * message, and the notes + scorecard panel for whichever stage is active. */
export function StageTabs({ candidate, onCandidateChange, onError }: StageTabsProps) {
  const [activeTemplateId, setActiveTemplateId] = useState<number | null>(
    candidate.stages[0]?.meeting_stage_template_id ?? null,
  )
  const [stageForm, setStageForm] = useState<{
    status: StageProgressStatus
    notes: string
    score_communication: number | null
    score_energy: number | null
    score_relevant_experience: number | null
  }>({ status: 'Upcoming', notes: '', score_communication: null, score_energy: null, score_relevant_experience: null })
  const [savingStage, setSavingStage] = useState(false)
  const stageSaved = useSavedFlash()

  const [showReschedule, setShowReschedule] = useState(false)
  const [rescheduleDate, setRescheduleDate] = useState('')
  const [rescheduleTime, setRescheduleTime] = useState('')

  const activeStage: CandidateStage | null =
    candidate.stages.find((s) => s.meeting_stage_template_id === activeTemplateId) ?? null

  useEffect(() => {
    if (!activeStage) return
    setStageForm({
      status: activeStage.status,
      notes: activeStage.notes ?? '',
      score_communication: activeStage.score_communication,
      score_energy: activeStage.score_energy,
      score_relevant_experience: activeStage.score_relevant_experience,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStage?.meeting_stage_template_id, activeStage?.status, activeStage?.notes])

  async function handleSaveStage() {
    if (activeTemplateId == null) return
    setSavingStage(true)
    try {
      onCandidateChange(await api.updateStageProgress(candidate.id, activeTemplateId, stageForm))
      stageSaved.flash()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to save stage')
    } finally {
      setSavingStage(false)
    }
  }

  async function handleCancelStage() {
    if (activeTemplateId == null) return
    if (!confirm('Cancel this stage?')) return
    try {
      onCandidateChange(await api.updateStageProgress(candidate.id, activeTemplateId, { status: 'Cancelled' }))
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to cancel stage')
    }
  }

  function openReschedule() {
    if (activeStage?.scheduled_at) {
      setRescheduleDate(toLocalDateValue(activeStage.scheduled_at))
      setRescheduleTime(toLocalTimeValue(activeStage.scheduled_at))
    } else {
      setRescheduleDate('')
      setRescheduleTime('')
    }
    setShowReschedule(true)
  }

  async function handleRescheduleSave(e: FormEvent) {
    e.preventDefault()
    if (activeTemplateId == null || !rescheduleDate || !rescheduleTime) return
    try {
      onCandidateChange(
        await api.updateStageProgress(candidate.id, activeTemplateId, {
          status: 'Upcoming',
          scheduled_at: new Date(`${rescheduleDate}T${rescheduleTime}`).toISOString(),
        }),
      )
      setShowReschedule(false)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to reschedule')
    }
  }

  function handleSendMessage() {
    window.open(`mailto:${candidate.email}`)
  }

  if (candidate.stages.length === 0) return null

  return (
    <div className="card section">
      <div className="tab-list">
        {candidate.stages.map((s) => (
          <button
            key={s.meeting_stage_template_id}
            type="button"
            className={`tab-button${s.meeting_stage_template_id === activeTemplateId ? ' active' : ''}`}
            onClick={() => setActiveTemplateId(s.meeting_stage_template_id)}
          >
            {s.stage_name}
          </button>
        ))}
      </div>

      {activeStage && (
        <div className="stage-tab-content">
          <p className="subtle">Stage</p>
          <div className="stage-tab-heading">
            <strong>{activeStage.stage_name}</strong>
            <span className={`status-badge status-${activeStage.status.replace(/\s+/g, '-').toLowerCase()}`}>
              {activeStage.status}
            </span>
          </div>
          {activeStage.scheduled_at ? (
            <p>Scheduled for {formatDateTime(activeStage.scheduled_at)}</p>
          ) : (
            <p className="subtle">Not yet scheduled</p>
          )}
          {candidate.source && <p className="subtle">Source: {candidate.source}</p>}

          <div className="page-header-actions" style={{ marginBottom: '1rem' }}>
            <button type="button" className="button-secondary" onClick={handleCancelStage}>
              Cancel
            </button>
            <button type="button" className="button-secondary" onClick={openReschedule}>
              Reschedule
            </button>
            <button type="button" className="button-secondary" onClick={handleSendMessage}>
              Send message
            </button>
          </div>

          <div className="interview-review">
            <div className="video-placeholder">Recording not available</div>
            <div className="interview-review-fields">
              <label>
                Status
                <select
                  value={stageForm.status}
                  onChange={(e) => setStageForm((f) => ({ ...f, status: e.target.value as StageProgressStatus }))}
                >
                  {STAGE_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Notes
                <textarea
                  rows={4}
                  value={stageForm.notes}
                  onChange={(e) => setStageForm((f) => ({ ...f, notes: e.target.value }))}
                />
              </label>

              <div className="score-card">
                <h3>Score card</h3>
                <ScoreRow
                  label="Communication"
                  value={stageForm.score_communication}
                  onChange={(n) => setStageForm((f) => ({ ...f, score_communication: n }))}
                />
                <ScoreRow
                  label="Energy"
                  value={stageForm.score_energy}
                  onChange={(n) => setStageForm((f) => ({ ...f, score_energy: n }))}
                />
                <ScoreRow
                  label="Relevant experience"
                  value={stageForm.score_relevant_experience}
                  onChange={(n) => setStageForm((f) => ({ ...f, score_relevant_experience: n }))}
                />
              </div>

              <div className="save-control">
                <button type="button" onClick={handleSaveStage} disabled={savingStage}>
                  {savingStage ? 'Saving…' : 'Save'}
                </button>
                {stageSaved.saved && <span className="save-confirmation">✓ Saved</span>}
              </div>
            </div>
          </div>
        </div>
      )}

      {showReschedule && (
        <Modal title="Reschedule" onClose={() => setShowReschedule(false)}>
          <form onSubmit={handleRescheduleSave} className="form">
            <div className="form-row">
              <label>
                New date
                <input
                  type="date"
                  value={rescheduleDate}
                  onChange={(e) => setRescheduleDate(e.target.value)}
                  required
                />
              </label>
              <label>
                New time
                <input
                  type="time"
                  value={rescheduleTime}
                  onChange={(e) => setRescheduleTime(e.target.value)}
                  required
                />
              </label>
            </div>
            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setShowReschedule(false)}>
                Cancel
              </button>
              <button type="submit">Save</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

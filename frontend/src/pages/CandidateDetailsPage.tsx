import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, saveBlob, openBlob } from '../api/client'
import { Modal } from '../components/Modal'
import { useSavedFlash } from '../hooks/useSavedFlash'
import type {
  CandidateDetail,
  CandidateDocumentChecklistItem,
  CandidateDocumentType,
  CandidateStage,
  Job,
  StageProgressStatus,
} from '../api/types'

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

export function CandidateDetailsPage() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [candidate, setCandidate] = useState<CandidateDetail | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const shareFlash = useSavedFlash(1500)

  const [editingInfo, setEditingInfo] = useState(false)
  const [infoForm, setInfoForm] = useState({
    name: '', email: '', phone: '', city: '', state: '', source: '', jobId: '',
  })
  const [savingInfo, setSavingInfo] = useState(false)

  const [uploadingResume, setUploadingResume] = useState(false)

  const [docChecklist, setDocChecklist] = useState<CandidateDocumentChecklistItem[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [uploadingDocType, setUploadingDocType] = useState<CandidateDocumentType | null>(null)

  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [savingAnswers, setSavingAnswers] = useState(false)
  const answersSaved = useSavedFlash()

  const [activeTemplateId, setActiveTemplateId] = useState<number | null>(null)
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

  async function load() {
    if (!candidateId) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.getCandidate(Number(candidateId))
      setCandidate(data)
      setActiveTemplateId((prev) => prev ?? data.stages[0]?.meeting_stage_template_id ?? null)
      const answersMap: Record<number, string> = {}
      data.screening_answers.forEach((a) => {
        answersMap[a.question_id] = a.answer_text ?? ''
      })
      setAnswers(answersMap)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load candidate')
    } finally {
      setLoading(false)
    }
  }

  async function loadDocs() {
    if (!candidateId) return
    setLoadingDocs(true)
    try {
      setDocChecklist(await api.listDocumentChecklist(Number(candidateId)))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load onboarding documents')
    } finally {
      setLoadingDocs(false)
    }
  }

  useEffect(() => {
    load()
    loadDocs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId])

  useEffect(() => {
    api.listJobs().then(setJobs).catch(() => {})
  }, [])

  const activeStage: CandidateStage | null =
    candidate?.stages.find((s) => s.meeting_stage_template_id === activeTemplateId) ?? null

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

  function openInfoEdit() {
    if (!candidate) return
    setInfoForm({
      name: candidate.name,
      email: candidate.email,
      phone: candidate.phone ?? '',
      city: candidate.city ?? '',
      state: candidate.state ?? '',
      source: candidate.source ?? '',
      jobId: candidate.job_id ? String(candidate.job_id) : '',
    })
    setEditingInfo(true)
  }

  async function handleInfoSave(e: FormEvent) {
    e.preventDefault()
    if (!candidate) return
    setSavingInfo(true)
    setError(null)
    try {
      const updated = await api.updateCandidate(candidate.id, {
        name: infoForm.name,
        email: infoForm.email,
        phone: infoForm.phone || null,
        city: infoForm.city || null,
        state: infoForm.state || null,
        source: infoForm.source || null,
        job_id: infoForm.jobId ? Number(infoForm.jobId) : null,
      })
      setCandidate(updated)
      setEditingInfo(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update candidate')
    } finally {
      setSavingInfo(false)
    }
  }

  async function handleDelete() {
    if (!candidate || !confirm(`Delete "${candidate.name}"? This cannot be undone.`)) return
    try {
      await api.deleteCandidate(candidate.id)
      navigate('/candidates')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete candidate')
    }
  }

  function copyText(text: string) {
    navigator.clipboard?.writeText(text).catch(() => {})
  }

  function handleShare() {
    copyText(window.location.href)
    shareFlash.flash()
  }

  async function handleResumeUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !candidate) return
    setUploadingResume(true)
    setError(null)
    try {
      setCandidate(await api.uploadResume(candidate.id, file))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to upload resume')
    } finally {
      setUploadingResume(false)
    }
  }

  async function handleViewResume() {
    if (!candidate) return
    try {
      const { blob } = await api.downloadResume(candidate.id)
      openBlob(blob)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to open resume')
    }
  }

  async function handleDocUpload(docType: CandidateDocumentType, e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !candidate) return
    setUploadingDocType(docType)
    setError(null)
    try {
      await api.uploadDocument(candidate.id, docType, file)
      await loadDocs()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to upload document')
    } finally {
      setUploadingDocType(null)
    }
  }

  async function handleDownloadDoc(docType: CandidateDocumentType, filename: string) {
    if (!candidate) return
    try {
      const { blob } = await api.downloadDocument(candidate.id, docType)
      saveBlob(blob, filename)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to download document')
    }
  }

  async function handleDownloadAll() {
    if (!candidate) return
    try {
      const { blob } = await api.downloadAllDocuments(candidate.id)
      saveBlob(blob, `${candidate.name} - documents.zip`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to download documents')
    }
  }

  function handleAnswerChange(questionId: number, text: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: text }))
  }

  async function handleSaveAnswers() {
    if (!candidate) return
    setSavingAnswers(true)
    setError(null)
    try {
      const payload = Object.entries(answers).map(([questionId, answerText]) => ({
        question_id: Number(questionId),
        answer_text: answerText,
      }))
      setCandidate(await api.updateScreeningAnswers(candidate.id, payload))
      answersSaved.flash()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save answers')
    } finally {
      setSavingAnswers(false)
    }
  }

  async function handleSaveStage() {
    if (!candidate || activeTemplateId == null) return
    setSavingStage(true)
    setError(null)
    try {
      setCandidate(await api.updateStageProgress(candidate.id, activeTemplateId, stageForm))
      stageSaved.flash()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save stage')
    } finally {
      setSavingStage(false)
    }
  }

  async function handleCancelStage() {
    if (!candidate || activeTemplateId == null) return
    if (!confirm('Cancel this stage?')) return
    setError(null)
    try {
      setCandidate(await api.updateStageProgress(candidate.id, activeTemplateId, { status: 'Cancelled' }))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to cancel stage')
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
    if (!candidate || activeTemplateId == null || !rescheduleDate || !rescheduleTime) return
    setError(null)
    try {
      setCandidate(
        await api.updateStageProgress(candidate.id, activeTemplateId, {
          status: 'Upcoming',
          scheduled_at: new Date(`${rescheduleDate}T${rescheduleTime}`).toISOString(),
        }),
      )
      setShowReschedule(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to reschedule')
    }
  }

  function handleSendMessage() {
    if (!candidate) return
    window.open(`mailto:${candidate.email}`)
  }

  if (loading && !candidate) {
    return (
      <div className="page">
        <p className="subtle">Loading…</p>
      </div>
    )
  }

  if (!candidate) {
    return (
      <div className="page">
        {error && <div className="error-banner">{error}</div>}
      </div>
    )
  }

  return (
    <div className="page candidate-details">
      <div className="candidate-toolbar">
        <Link to="/candidates" className="link-button">
          Close
        </Link>
        <div className="save-control">
          <button type="button" className="button-secondary" onClick={handleShare}>
            Share
          </button>
          {shareFlash.saved && <span className="save-confirmation">✓ Link copied</span>}
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="candidate-header-row">
        <div>
          <h1>
            {candidate.name}
            <button type="button" className="icon-button" onClick={openInfoEdit} aria-label="Edit candidate">
              ✎
            </button>
          </h1>
          <p className="subtle">Job</p>
          <p className="candidate-job-title">{candidate.job_title ?? '—'}</p>
        </div>
        <div className="candidate-contact">
          <div className="candidate-contact-row">
            <a href={`mailto:${candidate.email}`}>{candidate.email}</a>
            <button type="button" className="icon-button" onClick={() => copyText(candidate.email)} aria-label="Copy email">
              ⧉
            </button>
          </div>
          {candidate.phone && (
            <div className="candidate-contact-row">
              <span>{candidate.phone}</span>
              <button type="button" className="icon-button" onClick={() => copyText(candidate.phone!)} aria-label="Copy phone">
                ⧉
              </button>
            </div>
          )}
          {candidate.location && (
            <div className="candidate-contact-row">
              <span>Location: {candidate.location}</span>
              <button type="button" className="icon-button" onClick={() => copyText(candidate.location!)} aria-label="Copy location">
                ⧉
              </button>
            </div>
          )}
          <div className="candidate-contact-row">
            {candidate.has_resume ? (
              <button type="button" className="link-button" onClick={handleViewResume}>
                View resume
              </button>
            ) : (
              <label className="link-button">
                {uploadingResume ? 'Uploading…' : 'Upload resume'}
                <input type="file" hidden onChange={handleResumeUpload} disabled={uploadingResume} />
              </label>
            )}
          </div>
        </div>
      </div>

      {candidate.stages.length > 0 && (
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
        </div>
      )}

      <div className="card section">
        <div className="section-header">
          <h2>Onboarding information</h2>
          <button type="button" className="link-button" onClick={handleDownloadAll}>
            Download all ⬇
          </button>
        </div>
        <p className="subtle">Required information</p>
        {loadingDocs ? (
          <p className="subtle">Loading…</p>
        ) : (
          <div className="document-list">
            {docChecklist.map((item) => (
              <div key={item.doc_type} className="document-row">
                <strong>{item.label}</strong>
                {item.submission ? (
                  <p>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => handleDownloadDoc(item.doc_type, item.submission!.original_filename)}
                    >
                      {item.submission.original_filename}
                    </button>
                  </p>
                ) : (
                  <p className="subtle">No submission</p>
                )}
                <label className="link-button">
                  {uploadingDocType === item.doc_type ? 'Uploading…' : 'Upload ⬆'}
                  <input
                    type="file"
                    hidden
                    onChange={(e) => handleDocUpload(item.doc_type, e)}
                    disabled={uploadingDocType === item.doc_type}
                  />
                </label>
              </div>
            ))}
          </div>
        )}
      </div>

      {candidate.screening_answers.length > 0 && (
        <div className="card section">
          <div className="section-header">
            <h2>Pre-screening questions</h2>
            <div className="save-control">
              <button type="button" onClick={handleSaveAnswers} disabled={savingAnswers}>
                {savingAnswers ? 'Saving…' : 'Save'}
              </button>
              {answersSaved.saved && <span className="save-confirmation">✓ Saved</span>}
            </div>
          </div>
          <div className="screening-list">
            {candidate.screening_answers.map((a) => {
              const value = answers[a.question_id] ?? ''
              return (
                <div key={a.question_id} className="screening-row">
                  <span className={`screening-check${value.trim() ? ' answered' : ''}`}>✓</span>
                  <div className="screening-row-body">
                    <strong>{a.question_text}</strong>
                    <input value={value} onChange={(e) => handleAnswerChange(a.question_id, e.target.value)} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <button className="link-button danger" onClick={handleDelete}>
        Delete candidate
      </button>

      {editingInfo && (
        <Modal title="Edit candidate" onClose={() => setEditingInfo(false)}>
          <form onSubmit={handleInfoSave} className="form">
            <label>
              Name
              <input value={infoForm.name} onChange={(e) => setInfoForm((f) => ({ ...f, name: e.target.value }))} required />
            </label>
            <label>
              Email
              <input
                type="email"
                value={infoForm.email}
                onChange={(e) => setInfoForm((f) => ({ ...f, email: e.target.value }))}
                required
              />
            </label>
            <label>
              Phone
              <input value={infoForm.phone} onChange={(e) => setInfoForm((f) => ({ ...f, phone: e.target.value }))} />
            </label>
            <div className="form-row">
              <label>
                City
                <input value={infoForm.city} onChange={(e) => setInfoForm((f) => ({ ...f, city: e.target.value }))} />
              </label>
              <label>
                State
                <input value={infoForm.state} onChange={(e) => setInfoForm((f) => ({ ...f, state: e.target.value }))} />
              </label>
            </div>
            <label>
              Source
              <input
                value={infoForm.source}
                onChange={(e) => setInfoForm((f) => ({ ...f, source: e.target.value }))}
                placeholder="e.g. Indeed, Referral"
              />
            </label>
            <label>
              Job
              <select value={infoForm.jobId} onChange={(e) => setInfoForm((f) => ({ ...f, jobId: e.target.value }))}>
                <option value="">Unassigned</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.title}
                  </option>
                ))}
              </select>
            </label>
            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setEditingInfo(false)}>
                Cancel
              </button>
              <button type="submit" disabled={savingInfo}>
                {savingInfo ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </Modal>
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

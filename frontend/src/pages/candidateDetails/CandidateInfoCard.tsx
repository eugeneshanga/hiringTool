import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { api, ApiError, openBlob } from '../../api/client'
import { Modal } from '../../components/Modal'
import { copyText } from '../../lib/clipboard'
import { formatPhone } from '../../lib/formatPhone'
import type { CandidateDetail, Job } from '../../api/types'

interface CandidateInfoCardProps {
  candidate: CandidateDetail
  onCandidateChange: (candidate: CandidateDetail) => void
  onError: (message: string) => void
}

/** Name/job header + contact block (email, phone, location, resume) at the
 * top of the candidate details page, with its own "edit candidate" modal. */
export function CandidateInfoCard({ candidate, onCandidateChange, onError }: CandidateInfoCardProps) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [editingInfo, setEditingInfo] = useState(false)
  const [infoForm, setInfoForm] = useState({
    name: '', email: '', phone: '', city: '', state: '', source: '', jobId: '',
  })
  const [savingInfo, setSavingInfo] = useState(false)
  const [uploadingResume, setUploadingResume] = useState(false)

  useEffect(() => {
    api.listJobs().then(setJobs).catch(() => {})
  }, [])

  function openInfoEdit() {
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
    setSavingInfo(true)
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
      onCandidateChange(updated)
      setEditingInfo(false)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to update candidate')
    } finally {
      setSavingInfo(false)
    }
  }

  async function handleResumeUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploadingResume(true)
    try {
      onCandidateChange(await api.uploadResume(candidate.id, file))
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to upload resume')
    } finally {
      setUploadingResume(false)
    }
  }

  async function handleViewResume() {
    try {
      const { blob } = await api.downloadResume(candidate.id)
      openBlob(blob)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to open resume')
    }
  }

  return (
    <>
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
              <span>{formatPhone(candidate.phone)}</span>
              <button
                type="button"
                className="icon-button"
                onClick={() => copyText(formatPhone(candidate.phone))}
                aria-label="Copy phone"
              >
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
    </>
  )
}

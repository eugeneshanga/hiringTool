import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import { usePageTitle } from '../hooks/usePageTitle'
import type { Job } from '../api/types'

export interface JobDetailContext {
  job: Job
  reloadJob: () => Promise<void>
}

export function useJobDetailContext() {
  return useOutletContext<JobDetailContext>()
}

export function JobDetailLayout() {
  const { jobId } = useParams()
  const [job, setJob] = useState<Job | null>(null)
  usePageTitle(job ? `${job.title} - HiringTool` : 'Job - HiringTool')
  const [error, setError] = useState<string | null>(null)

  const [editingTitle, setEditingTitle] = useState(false)
  const [titleInput, setTitleInput] = useState('')
  const [savingTitle, setSavingTitle] = useState(false)

  const load = useCallback(async () => {
    if (!jobId) return
    try {
      const data = await api.getJob(Number(jobId))
      setJob(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load job')
    }
  }, [jobId])

  useEffect(() => {
    load()
  }, [load])

  function openTitleEdit() {
    if (!job) return
    setTitleInput(job.title)
    setEditingTitle(true)
  }

  async function handleTitleSave(e: FormEvent) {
    e.preventDefault()
    if (!job || !titleInput.trim()) return
    setSavingTitle(true)
    setError(null)
    try {
      await api.updateJob(job.id, { title: titleInput.trim() })
      await load()
      setEditingTitle(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update job title')
    } finally {
      setSavingTitle(false)
    }
  }

  if (error) {
    return (
      <div className="page">
        <div className="error-banner">{error}</div>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="page">
        <p className="subtle">Loading…</p>
      </div>
    )
  }

  return (
    <div className="job-detail">
      <div className="job-detail-body">
        <aside className="job-detail-sidebar">
          <Link to="/jobs" className="link-button back-link">
            ‹ Back
          </Link>
          <div className="sidebar-group-label">Job Editor</div>
          <NavLink to={`/jobs/${job.id}`} end className={({ isActive }) => (isActive ? 'active' : '')}>
            Job details
          </NavLink>
          <NavLink
            to={`/jobs/${job.id}/meeting-stages`}
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            Meeting stages
          </NavLink>
        </aside>
        <div className="job-detail-content">
          <div className="job-detail-title-row">
            <h1>
              {job.title}
              <button
                type="button"
                className="icon-button"
                onClick={openTitleEdit}
                aria-label="Edit job title"
              >
                ✎
              </button>
            </h1>
            {job.location && <p className="subtle">{job.location}</p>}
          </div>
          <Outlet context={{ job, reloadJob: load } satisfies JobDetailContext} />
        </div>
      </div>

      {editingTitle && (
        <Modal title="Edit job title" onClose={() => setEditingTitle(false)}>
          <form onSubmit={handleTitleSave} className="form">
            <label>
              Job title
              <input value={titleInput} onChange={(e) => setTitleInput(e.target.value)} required autoFocus />
            </label>
            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setEditingTitle(false)}>
                Cancel
              </button>
              <button type="submit" disabled={savingTitle || !titleInput.trim()}>
                {savingTitle ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

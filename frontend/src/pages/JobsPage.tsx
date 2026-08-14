import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Job, JobStatus } from '../api/types'

const STATUSES: JobStatus[] = ['Published', 'Draft', 'Closed']

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export function JobsPage() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState<Job[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listJobs({
        status: statusFilter || undefined,
        search: search || undefined,
      })
      setJobs(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load jobs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timeout = setTimeout(load, search ? 300 : 0)
    return () => clearTimeout(timeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, statusFilter])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const job = await api.createJob({ title })
      navigate(`/jobs/${job.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create job')
      setSubmitting(false)
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Jobs</h1>
        <div className="page-header-actions">
          <button onClick={() => setShowForm((v) => !v)}>{showForm ? 'Cancel' : 'Add job'}</button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showForm && (
        <form className="card form" onSubmit={handleCreate}>
          <label>
            Job title
            <input value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? 'Creating…' : 'Create job'}
          </button>
        </form>
      )}

      <div className="page-header-actions" style={{ marginBottom: '1rem' }}>
        <input
          placeholder="Search jobs…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : jobs.length === 0 ? (
        <p className="subtle">No jobs yet.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Create date</th>
              <th>Job</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="clickable-row" onClick={() => navigate(`/jobs/${job.id}`)}>
                <td>{formatDate(job.created_at)}</td>
                <td>
                  <strong>{job.title}</strong>
                  {job.location && <div className="subtle">{job.location}</div>}
                  {job.meeting_stages.length > 0 && (
                    <div className="chip-list">
                      {job.meeting_stages.map((stage) => (
                        <span key={stage.id} className="chip-row">
                          <span className="chip">{stage.meeting_type}</span> {stage.stage_name}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td>{job.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

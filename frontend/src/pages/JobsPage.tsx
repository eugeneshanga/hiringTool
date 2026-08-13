import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { Job, JobStatus } from '../api/types'

const STATUSES: JobStatus[] = ['Open', 'Closed', 'Draft']

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  const [title, setTitle] = useState('')
  const [department, setDepartment] = useState('')
  const [location, setLocation] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listJobs(statusFilter ? { status: statusFilter } : undefined)
      setJobs(data)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load jobs')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.createJob({
        title,
        department: department || null,
        location: location || null,
        description: description || null,
      })
      setTitle('')
      setDepartment('')
      setLocation('')
      setDescription('')
      setShowForm(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create job')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleStatusChange(job: Job, status: JobStatus) {
    try {
      await api.updateJob(job.id, { status })
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update job')
    }
  }

  async function handleDelete(job: Job) {
    if (!confirm(`Delete "${job.title}"? This cannot be undone.`)) return
    try {
      await api.deleteJob(job.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete job')
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Jobs</h1>
        <div className="page-header-actions">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : 'New job'}
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showForm && (
        <form className="card form" onSubmit={handleCreate}>
          <div className="form-row">
            <label>
              Title
              <input value={title} onChange={(e) => setTitle(e.target.value)} required />
            </label>
            <label>
              Department
              <input value={department} onChange={(e) => setDepartment(e.target.value)} />
            </label>
            <label>
              Location
              <input value={location} onChange={(e) => setLocation(e.target.value)} />
            </label>
          </div>
          <label>
            Description
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
          </label>
          <button type="submit" disabled={submitting}>
            {submitting ? 'Creating…' : 'Create job'}
          </button>
        </form>
      )}

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : jobs.length === 0 ? (
        <p className="subtle">No jobs yet.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Title</th>
              <th>Department</th>
              <th>Location</th>
              <th>Candidates</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>{job.title}</td>
                <td>{job.department ?? '—'}</td>
                <td>{job.location ?? '—'}</td>
                <td>{job.candidate_count}</td>
                <td>
                  <select
                    value={job.status}
                    onChange={(e) => handleStatusChange(job, e.target.value as JobStatus)}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <button className="link-button danger" onClick={() => handleDelete(job)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

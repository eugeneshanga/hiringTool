import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { Candidate, Job, Stage } from '../api/types'

const STAGES: Stage[] = ['Applied', 'Interview', 'Offer', 'Hired', 'Rejected']

export function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [search, setSearch] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [jobId, setJobId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {1
      const [candidateData, jobData] = await Promise.all([
        api.listCandidates({
          search: search || undefined,
          stage: stageFilter || undefined,
        }),
        api.listJobs(),
      ])
      setCandidates(candidateData)
      setJobs(jobData)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load candidates')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timeout = setTimeout(load, search ? 300 : 0)
    return () => clearTimeout(timeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, stageFilter])

  function jobTitle(id: number | null) {
    if (id === null) return '—'
    return jobs.find((j) => j.id === id)?.title ?? `#${id}`
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.createCandidate({
        name,
        email,
        phone: phone || null,
        job_id: jobId ? Number(jobId) : null,
      })
      setName('')
      setEmail('')
      setPhone('')
      setJobId('')
      setShowForm(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create candidate')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleStageChange(candidate: Candidate, stage: Stage) {
    try {
      await api.updateCandidate(candidate.id, { stage })
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update candidate')
    }
  }

  async function handleDelete(candidate: Candidate) {
    if (!confirm(`Delete "${candidate.name}"? This cannot be undone.`)) return
    try {
      await api.deleteCandidate(candidate.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete candidate')
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Candidates</h1>
        <div className="page-header-actions">
          <input
            placeholder="Search name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select value={stageFilter} onChange={(e) => setStageFilter(e.target.value)}>
            <option value="">All stages</option>
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <button onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : 'New candidate'}
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {showForm && (
        <form className="card form" onSubmit={handleCreate}>
          <div className="form-row">
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label>
              Phone
              <input value={phone} onChange={(e) => setPhone(e.target.value)} />
            </label>
            <label>
              Job
              <select value={jobId} onChange={(e) => setJobId(e.target.value)}>
                <option value="">Unassigned</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button type="submit" disabled={submitting}>
            {submitting ? 'Creating…' : 'Create candidate'}
          </button>
        </form>
      )}

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : candidates.length === 0 ? (
        <p className="subtle">No candidates match.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Job</th>
              <th>Stage</th>
              <th>Interviewer</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.email}</td>
                <td>{jobTitle(c.job_id)}</td>
                <td>
                  <select
                    value={c.stage}
                    onChange={(e) => handleStageChange(c, e.target.value as Stage)}
                  >
                    {STAGES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{c.interviewer ?? '—'}</td>
                <td>
                  <button className="link-button danger" onClick={() => handleDelete(c)}>
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

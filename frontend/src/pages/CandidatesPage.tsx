import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, saveBlob } from '../api/client'
import type { Candidate, Job, Stage } from '../api/types'
import { formatPhone } from '../lib/formatPhone'

const STAGES: Stage[] = ['Applied', 'Interview', 'Offer', 'Hired', 'Rejected']

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function csvCell(value: string) {
  return `"${value.replace(/"/g, '""')}"`
}

export function CandidatesPage() {
  const navigate = useNavigate()
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [search, setSearch] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [showFilters, setShowFilters] = useState(false)
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
    try {
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

  async function handleDelete(candidate: Candidate) {
    if (!confirm(`Delete "${candidate.name}"? This cannot be undone.`)) return
    try {
      await api.deleteCandidate(candidate.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete candidate')
    }
  }

  const rows = useMemo(
    () =>
      candidates.map((c) => ({
        candidate: c,
        stageLabel: c.current_stage?.stage_name ?? c.stage,
        statusLabel: c.current_stage?.status ?? c.status,
        scheduledLabel: c.current_stage?.scheduled_at ?? null,
      })),
    [candidates],
  )

  function handleExport() {
    const header = ['Candidate', 'Job', 'Stage', 'Updated', 'Scheduled', 'Interviewer', 'Status']
    const lines = rows.map(({ candidate: c, stageLabel, statusLabel, scheduledLabel }) =>
      [c.name, c.job_title ?? '', stageLabel, formatDate(c.updated_at), formatDate(scheduledLabel), c.interviewer ?? '', statusLabel]
        .map((v) => csvCell(String(v)))
        .join(','),
    )
    const csv = [header.map(csvCell).join(','), ...lines].join('\n')
    saveBlob(new Blob([csv], { type: 'text/csv' }), 'candidates.csv')
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Candidates</h1>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="card">
        <div className="candidates-toolbar">
          <button
            type="button"
            className="button-secondary"
            aria-pressed={showFilters}
            onClick={() => setShowFilters((v) => !v)}
          >
            ⏷ Filters
          </button>
          <input
            className="candidates-search"
            placeholder="Search name/email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="candidates-toolbar-spacer" />
          <button type="button" className="button-secondary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? 'Cancel' : 'New candidate'}
          </button>
          <button type="button" className="button-secondary" onClick={handleExport} disabled={rows.length === 0}>
            Export
          </button>
        </div>

        {showFilters && (
          <div className="form-row candidates-filters">
            <label>
              Stage
              <select value={stageFilter} onChange={(e) => setStageFilter(e.target.value)}>
                <option value="">All stages</option>
                {STAGES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        {showForm && (
          <form className="form candidates-create-form" onSubmit={handleCreate}>
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
        ) : rows.length === 0 ? (
          <p className="subtle">No candidates match.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Job</th>
                <th>Stage</th>
                <th>Updated</th>
                <th>Scheduled</th>
                <th>Interviewer</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ candidate: c, stageLabel, statusLabel, scheduledLabel }) => (
                <tr key={c.id} className="clickable-row" onClick={() => navigate(`/candidates/${c.id}`)}>
                  <td>
                    <div className="candidate-cell">
                      <div className="candidate-cell-name">
                        {c.name}
                        {c.candidate_account_id != null && (
                          <span
                            className="chip"
                            style={{ marginLeft: '0.5rem' }}
                            title="Created their own account by registering"
                          >
                            Self-registered
                          </span>
                        )}
                      </div>
                      <div className="candidate-cell-contact subtle">
                        <div>{c.email}</div>
                        {c.phone && <div>{formatPhone(c.phone)}</div>}
                      </div>
                    </div>
                  </td>
                  <td>{c.job_title ?? '—'}</td>
                  <td>{stageLabel}</td>
                  <td>{formatDate(c.updated_at)}</td>
                  <td>{formatDate(scheduledLabel)}</td>
                  <td>{c.interviewer ?? '—'}</td>
                  <td>
                    <strong>{statusLabel}</strong>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
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
    </div>
  )
}

import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { JobStatus, JobType, SalaryPeriod } from '../api/types'
import { useSavedFlash } from '../hooks/useSavedFlash'
import { useJobDetailContext } from './JobDetailLayout'

const STATUSES: JobStatus[] = ['Published', 'Draft', 'Closed']
const JOB_TYPES: JobType[] = ['Full-time', 'Part-time', 'Remote']
const SALARY_PERIODS: SalaryPeriod[] = ['Hourly', 'Salary']

export function JobDetailsPage() {
  const { job, reloadJob } = useJobDetailContext()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  const [status, setStatus] = useState<JobStatus>(job.status)
  const [savingStatus, setSavingStatus] = useState(false)
  const statusSaved = useSavedFlash()

  const [jobType, setJobType] = useState<JobType[]>(job.job_type)
  const [city, setCity] = useState(job.city ?? '')
  const [state, setState] = useState(job.state ?? '')
  const [postalCode, setPostalCode] = useState(job.postal_code ?? '')
  const [country, setCountry] = useState(job.country ?? 'USA')
  const [minSalary, setMinSalary] = useState(job.min_salary?.toString() ?? '')
  const [maxSalary, setMaxSalary] = useState(job.max_salary?.toString() ?? '')
  const [salaryPeriod, setSalaryPeriod] = useState<SalaryPeriod | ''>(job.salary_period ?? '')
  const [highlights, setHighlights] = useState<string[]>(job.highlights)
  const [highlightInput, setHighlightInput] = useState('')
  const [description, setDescription] = useState(job.description ?? '')
  const [savingDetails, setSavingDetails] = useState(false)
  const detailsSaved = useSavedFlash()

  async function handleStatusSave() {
    setSavingStatus(true)
    setError(null)
    try {
      await api.updateJob(job.id, { status })
      await reloadJob()
      statusSaved.flash()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update status')
    } finally {
      setSavingStatus(false)
    }
  }

  function toggleJobType(type: JobType) {
    setJobType((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]))
  }

  function addHighlight(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return
    e.preventDefault()
    const value = highlightInput.trim()
    if (value && !highlights.includes(value)) {
      setHighlights((prev) => [...prev, value])
    }
    setHighlightInput('')
  }

  function removeHighlight(value: string) {
    setHighlights((prev) => prev.filter((h) => h !== value))
  }

  async function handleDetailsSave(e: FormEvent) {
    e.preventDefault()
    setSavingDetails(true)
    setError(null)
    try {
      await api.updateJob(job.id, {
        job_type: jobType,
        city: city || null,
        state: state || null,
        postal_code: postalCode || null,
        country: country || null,
        min_salary: minSalary ? Number(minSalary) : null,
        max_salary: maxSalary ? Number(maxSalary) : null,
        salary_period: salaryPeriod || null,
        highlights,
        description: description || null,
      })
      await reloadJob()
      detailsSaved.flash()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save job details')
    } finally {
      setSavingDetails(false)
    }
  }

  async function handleDeleteJob() {
    if (!confirm(`Delete "${job.title}"? This cannot be undone.`)) return
    try {
      await api.deleteJob(job.id)
      navigate('/jobs')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to delete job')
    }
  }

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}

      <div className="card section">
        <div className="section-header">
          <h2>Job status</h2>
          <div className="save-control">
            <button onClick={handleStatusSave} disabled={savingStatus || status === job.status}>
              {savingStatus ? 'Saving…' : 'Save'}
            </button>
            {statusSaved.saved && <span className="save-confirmation">✓ Saved</span>}
          </div>
        </div>
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value as JobStatus)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>

      <form className="card section" onSubmit={handleDetailsSave}>
        <div className="section-header">
          <h2>Job details</h2>
          <div className="save-control">
            <button type="submit" disabled={savingDetails}>
              {savingDetails ? 'Saving…' : 'Save'}
            </button>
            {detailsSaved.saved && <span className="save-confirmation">✓ Saved</span>}
          </div>
        </div>

        <label>Job type (select all that apply)</label>
        <div className="checkbox-row">
          {JOB_TYPES.map((type) => (
            <label key={type} className="checkbox-label">
              <input
                type="checkbox"
                checked={jobType.includes(type)}
                onChange={() => toggleJobType(type)}
              />
              {type}
            </label>
          ))}
        </div>

        <div className="form-row">
          <label>
            City
            <input value={city} onChange={(e) => setCity(e.target.value)} />
          </label>
          <label>
            State
            <input value={state} onChange={(e) => setState(e.target.value)} />
          </label>
        </div>
        <div className="form-row">
          <label>
            Postal code
            <input value={postalCode} onChange={(e) => setPostalCode(e.target.value)} />
          </label>
          <label>
            Country
            <input value={country} onChange={(e) => setCountry(e.target.value)} />
          </label>
        </div>

        <div className="form-row">
          <label>
            Minimum salary
            <input
              type="number"
              min={0}
              value={minSalary}
              onChange={(e) => setMinSalary(e.target.value)}
            />
          </label>
          <label>
            Maximum salary
            <input
              type="number"
              min={0}
              value={maxSalary}
              onChange={(e) => setMaxSalary(e.target.value)}
            />
          </label>
          <label>
            Period
            <select
              value={salaryPeriod}
              onChange={(e) => setSalaryPeriod(e.target.value as SalaryPeriod)}
            >
              <option value="">—</option>
              {SALARY_PERIODS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label>
          Job highlights (press Enter to add)
          <input
            value={highlightInput}
            onChange={(e) => setHighlightInput(e.target.value)}
            onKeyDown={addHighlight}
            placeholder="Add a highlight and press Enter"
          />
        </label>
        {highlights.length > 0 && (
          <div className="chip-list">
            {highlights.map((h) => (
              <span key={h} className="chip removable">
                {h}
                <button type="button" onClick={() => removeHighlight(h)} aria-label={`Remove ${h}`}>
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <label>
          Job description
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={8}
          />
        </label>
      </form>

      <button className="link-button danger" onClick={handleDeleteJob}>
        Delete job
      </button>
    </div>
  )
}

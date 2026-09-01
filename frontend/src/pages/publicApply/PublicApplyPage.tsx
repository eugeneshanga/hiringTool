import { useEffect, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { publicApplyApi, publicErrorMessage } from '../../api/publicApplyClient'
import { usePageTitle } from '../../hooks/usePageTitle'
import type { PublicJob } from '../../api/types'

type YesNo = 'yes' | 'no' | ''
type Tab = 'overview' | 'application'

// Matches the backend's app-wide MAX_CONTENT_LENGTH (config.py) - checked
// here too so a slow connection doesn't have to spend minutes uploading a
// file that was always going to be rejected. Approximate: the real limit is
// on the whole multipart request, resume plus a few negligible text fields,
// not the file alone - close enough not to matter in practice.
const MAX_RESUME_SIZE_BYTES = 15 * 1024 * 1024

function formatCompensation(job: PublicJob): string | null {
  if (job.min_salary == null && job.max_salary == null) return null
  const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 })
  const range =
    job.min_salary != null && job.max_salary != null
      ? `$${fmt(job.min_salary)} – $${fmt(job.max_salary)}`
      : `$${fmt(job.min_salary ?? job.max_salary!)}`
  const period = job.salary_period === 'Hourly' ? 'per hour' : job.salary_period === 'Salary' ? 'per year' : ''
  return [job.salary_period, range, period].filter(Boolean).join(' ')
}

/** Step 1 of the public apply flow (no login) — POST /api/apply. Reached by
 * a direct link to a specific job (`/apply/job/:jobId`); there's no public
 * job-browsing page linking here yet (see README's "Known gaps") — for now
 * this URL gets shared out manually, e.g. copied from the recruiter Jobs
 * page. A real success and a honeypot-tripped "success" render identically
 * on purpose — see publicApplyApi.apply and the backend's routes/apply.py.
 *
 * Layout: a job-details sidebar (location/job type/compensation/highlights)
 * that stays put across two tabs — Overview (the job description) and
 * Application (the form itself) — rather than one long scrolling page. */
export function PublicApplyPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const id = Number(jobId)

  const [job, setJob] = useState<PublicJob | null>(null)
  const [jobError, setJobError] = useState<string | null>(null)
  const [loadingJob, setLoadingJob] = useState(true)
  const [tab, setTab] = useState<Tab>('overview')

  usePageTitle(job ? `Apply - ${job.title}` : 'Apply')

  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [addressLine1, setAddressLine1] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [postalCode, setPostalCode] = useState('')
  const [resume, setResume] = useState<File | null>(null)
  const [resumeError, setResumeError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [workAuthorized, setWorkAuthorized] = useState<YesNo>('')
  const [requiresVisaSponsorship, setRequiresVisaSponsorship] = useState<YesNo>('')
  // Honeypot: invisible to a real applicant (see .honeypot-field in
  // index.css), present in the DOM for a bot's form-filler to trip over.
  const [website, setWebsite] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!Number.isFinite(id)) {
      setJobError('This application link is invalid.')
      setLoadingJob(false)
      return
    }
    let cancelled = false
    publicApplyApi
      .getJob(id)
      .then((data) => {
        if (!cancelled) setJob(data)
      })
      .catch((err) => {
        if (!cancelled) setJobError(publicErrorMessage(err, 'This job could not be found.'))
      })
      .finally(() => {
        if (!cancelled) setLoadingJob(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  function handleResumeChange(file: File | null) {
    if (file && file.size > MAX_RESUME_SIZE_BYTES) {
      setResume(null)
      setResumeError('That file is too large — please upload something under 15MB.')
      return
    }
    setResumeError(null)
    setResume(file)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!resume || !workAuthorized || !requiresVisaSponsorship) return
    setError(null)
    setSubmitting(true)
    try {
      await publicApplyApi.apply({
        first_name: firstName,
        last_name: lastName,
        email,
        phone: phone || undefined,
        address_line1: addressLine1 || undefined,
        city: city || undefined,
        state: state || undefined,
        postal_code: postalCode || undefined,
        job_id: id,
        resume,
        answers: Object.entries(answers).map(([questionId, answerText]) => ({
          question_id: Number(questionId),
          answer_text: answerText,
        })),
        work_authorized: workAuthorized,
        requires_visa_sponsorship: requiresVisaSponsorship,
        website,
      })
      setSubmitted(true)
    } catch (err) {
      setError(publicErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (loadingJob) return <div className="page-loading">Loading…</div>

  if (jobError) {
    return (
      <div className="public-page">
        <div className="card public-card">
          <h1>HiringTool</h1>
          <p className="error-banner">{jobError}</p>
        </div>
      </div>
    )
  }

  if (submitted) {
    return (
      <div className="public-page">
        <div className="card public-card">
          <h1>Thanks for applying{job ? ` to ${job.title}` : ''}!</h1>
          <p>We'll review your application and follow up by email with next steps.</p>
        </div>
      </div>
    )
  }

  if (!job) return null

  const compensation = formatCompensation(job)

  return (
    <div className="apply-page">
      <div className="apply-header">
        <h1>{job.title}</h1>
      </div>

      <div className="tab-list">
        <button type="button" className={`tab-button${tab === 'overview' ? ' active' : ''}`} onClick={() => setTab('overview')}>
          Overview
        </button>
        <button type="button" className={`tab-button${tab === 'application' ? ' active' : ''}`} onClick={() => setTab('application')}>
          Application
        </button>
      </div>

      <div className="apply-layout">
        <aside className="apply-sidebar">
          {job.location && (
            <div className="apply-sidebar-field">
              <p className="apply-sidebar-label">Location</p>
              <p className="apply-sidebar-value">{job.location}</p>
            </div>
          )}
          {job.job_type.length > 0 && (
            <div className="apply-sidebar-field">
              <p className="apply-sidebar-label">Job Type</p>
              <p className="apply-sidebar-value">{job.job_type.join(', ')}</p>
            </div>
          )}
          {compensation && (
            <div className="apply-sidebar-field">
              <p className="apply-sidebar-label">Compensation</p>
              <p className="apply-sidebar-value">{compensation}</p>
            </div>
          )}
          {job.highlights.length > 0 && (
            <div className="apply-sidebar-field">
              <p className="apply-sidebar-label">Highlights</p>
              <div className="chip-list chip-list-wrap">
                {job.highlights.map((h) => (
                  <span key={h} className="chip">
                    {h}
                  </span>
                ))}
              </div>
            </div>
          )}
        </aside>

        <main className="apply-main">
          {tab === 'overview' ? (
            <div>
              <h2 className="apply-section-heading apply-section-heading-first">About this role</h2>
              {job.description ? (
                <p className="public-job-description">{job.description}</p>
              ) : (
                <p className="subtle">No description provided.</p>
              )}
            </div>
          ) : (
            <form className="form" onSubmit={handleSubmit}>
              <h2 className="apply-section-heading apply-section-heading-first">Contact information</h2>
              <div className="form-row">
                <label>
                  First name
                  <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required autoFocus />
                </label>
                <label>
                  Last name
                  <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
                </label>
              </div>
              <label>
                Email
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </label>
              <label>
                Phone number
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </label>
              <label>
                Street address
                <input value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} />
              </label>
              <div className="form-row">
                <label>
                  City
                  <input value={city} onChange={(e) => setCity(e.target.value)} />
                </label>
                <label>
                  State
                  <input value={state} onChange={(e) => setState(e.target.value)} />
                </label>
                <label>
                  ZIP / Postal Code
                  <input value={postalCode} onChange={(e) => setPostalCode(e.target.value)} />
                </label>
              </div>
              <label>
                Resume
                <input
                  type="file"
                  accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(e) => handleResumeChange(e.target.files?.[0] ?? null)}
                  required
                />
              </label>
              {resumeError && <p className="field-error">{resumeError}</p>}

              {job.screening_questions.length > 0 && (
                <>
                  <h2 className="apply-section-heading">Screening questions</h2>
                  <div className="screening-list">
                    {job.screening_questions.map((q) => (
                      <label key={q.id}>
                        {q.question_text}
                        {q.answer_options.length > 0 ? (
                          <select
                            value={answers[q.id] ?? ''}
                            onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                            required
                          >
                            <option value="">Select an answer…</option>
                            {q.answer_options.map((option) => (
                              <option key={option} value={option}>
                                {option}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            value={answers[q.id] ?? ''}
                            onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                            required
                          />
                        )}
                      </label>
                    ))}
                  </div>
                </>
              )}

              <h2 className="apply-section-heading">Additional information</h2>
              <fieldset className="radio-list">
                <legend>Are you legally authorized to work in the country where this role is located?</legend>
                <label className="radio-option">
                  <input
                    type="radio"
                    name="work_authorized"
                    value="yes"
                    checked={workAuthorized === 'yes'}
                    onChange={() => setWorkAuthorized('yes')}
                    required
                  />
                  Yes
                </label>
                <label className="radio-option">
                  <input
                    type="radio"
                    name="work_authorized"
                    value="no"
                    checked={workAuthorized === 'no'}
                    onChange={() => setWorkAuthorized('no')}
                    required
                  />
                  No
                </label>
              </fieldset>
              <fieldset className="radio-list">
                <legend>
                  Will you now or in the future require visa sponsorship to work in the country where
                  this role is located?
                </legend>
                <label className="radio-option">
                  <input
                    type="radio"
                    name="requires_visa_sponsorship"
                    value="yes"
                    checked={requiresVisaSponsorship === 'yes'}
                    onChange={() => setRequiresVisaSponsorship('yes')}
                    required
                  />
                  Yes
                </label>
                <label className="radio-option">
                  <input
                    type="radio"
                    name="requires_visa_sponsorship"
                    value="no"
                    checked={requiresVisaSponsorship === 'no'}
                    onChange={() => setRequiresVisaSponsorship('no')}
                    required
                  />
                  No
                </label>
              </fieldset>

              <h2 className="apply-section-heading">U.S. Equal Employment Opportunity Information</h2>
              <p className="subtle eeo-notice">
                {job.organization_name} provides equal employment opportunities to applicants and
                employees without regard to race, color, religion, sex, sexual orientation, gender
                identity, national origin, protected veteran status, disability, or any other
                classification protected by applicable law.
              </p>

              <div className="honeypot-field" aria-hidden="true">
                <label>
                  Company website
                  <input
                    tabIndex={-1}
                    autoComplete="off"
                    value={website}
                    onChange={(e) => setWebsite(e.target.value)}
                  />
                </label>
              </div>

              {error && <div className="error-banner">{error}</div>}
              <button type="submit" disabled={submitting}>
                {submitting ? 'Submitting…' : 'Apply'}
              </button>
            </form>
          )}
        </main>
      </div>
    </div>
  )
}

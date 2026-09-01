import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useOrganizationBranding } from '../../hooks/useOrganizationBranding'
import { usePageTitle } from '../../hooks/usePageTitle'
import { publicApplyApi, publicErrorMessage } from '../../api/publicApplyClient'
import type { PublicJobSummary } from '../../api/types'

function formatCompensation(job: PublicJobSummary): string | null {
  if (job.min_salary == null && job.max_salary == null) return null
  const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 })
  const range =
    job.min_salary != null && job.max_salary != null
      ? `$${fmt(job.min_salary)} - $${fmt(job.max_salary)}`
      : `$${fmt(job.min_salary ?? job.max_salary!)}`
  const period = job.salary_period === 'Hourly' ? 'hourly' : job.salary_period === 'Salary' ? 'per year' : ''
  return [range, period].filter(Boolean).join(' ')
}

/** One row in the job list: title/meta on the left, the "Schedule
 * Interview" call-to-action and a plain-text "Direct Link" alternative on
 * the right (same destination, /apply/job/:id - the button is for a
 * candidate browsing this page, the plain link is what you'd copy out to
 * paste into a job board posting elsewhere), and an expand-in-place
 * "Show Details" accordion below rather than navigating away just to read
 * the description. */
function JobRow({ job }: { job: PublicJobSummary }) {
  const [expanded, setExpanded] = useState(false)
  const compensation = formatCompensation(job)
  const applyHref = `/apply/job/${job.id}`

  return (
    <div className="job-row">
      <div className="job-row-main">
        <div className="job-row-info">
          <h3>{job.title}</h3>
          <div className="job-row-meta">
            {job.job_type.length > 0 && <span>{job.job_type.join(', ')}</span>}
            {job.location && <span>{job.location}</span>}
            {compensation && <span>{compensation}</span>}
          </div>
        </div>
        <div className="job-row-actions">
          <Link to={applyHref} className="job-row-schedule-button">
            Schedule Interview
          </Link>
          <Link to={applyHref} className="link-button">
            Direct Link
          </Link>
        </div>
      </div>
      <button type="button" className="job-row-details-toggle" onClick={() => setExpanded((prev) => !prev)}>
        {expanded ? 'Hide Details' : 'Show Details'}
        <span className={`job-row-chevron${expanded ? ' up' : ''}`}>▾</span>
      </button>
      {expanded && (
        <div className="job-row-details">
          {job.description ? <p>{job.description}</p> : <p className="subtle">No description provided.</p>}
        </div>
      )}
    </div>
  )
}

/** The site's root ('/') — a candidate's default landing page, whether they
 * typed the domain directly or clicked a generic "see our openings" link
 * (as opposed to /apply/job/:jobId, which a specific job board posting
 * links straight to, bypassing this page entirely). Organization
 * name/logo (useOrganizationBranding, shared with PublicHeader) plus every
 * open job (GET /api/public/jobs) - see routes/public.py for why these are
 * a separate, minimal public contract rather than reusing the
 * recruiter-side /api/organization or Job.to_dict(). */
export function CareersLandingPage() {
  const { name, logoUrl, loaded: orgLoaded } = useOrganizationBranding()
  const [jobs, setJobs] = useState<PublicJobSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  usePageTitle(name ? `Careers - ${name}` : 'Careers')

  useEffect(() => {
    let cancelled = false
    publicApplyApi
      .listJobs()
      .then((data) => {
        if (!cancelled) setJobs(data)
      })
      .catch((err) => {
        if (!cancelled) setError(publicErrorMessage(err, 'Something went wrong loading this page.'))
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="landing-page">
      <div className="landing-hero">
        {logoUrl && <img src={logoUrl} alt="" className="landing-hero-logo" />}
        <h1>{orgLoaded ? name || 'Careers' : ' '}</h1>
        <p>Find your next opportunity with us</p>
      </div>

      <div className="landing-body">
        {error ? (
          <div className="card">
            <p className="error-banner">{error}</p>
          </div>
        ) : (
          <div className="card landing-jobs-card">
            <h2>Available Jobs</h2>
            {jobs === null ? (
              <p className="subtle">Loading…</p>
            ) : jobs.length === 0 ? (
              <p className="subtle">No open positions right now — please check back soon.</p>
            ) : (
              <div className="job-row-list">
                {jobs.map((job) => (
                  <JobRow key={job.id} job={job} />
                ))}
              </div>
            )}
          </div>
        )}

        <footer className="landing-footer">
          <Link to="/status">Already applied? Check your status</Link>
        </footer>
      </div>
    </div>
  )
}

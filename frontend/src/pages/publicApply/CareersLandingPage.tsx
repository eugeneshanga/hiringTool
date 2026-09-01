import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { publicApplyApi, publicErrorMessage } from '../../api/publicApplyClient'
import type { PublicJobSummary, PublicOrganizationInfo } from '../../api/types'

function formatCompensation(job: PublicJobSummary): string | null {
  if (job.min_salary == null && job.max_salary == null) return null
  const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 })
  const range =
    job.min_salary != null && job.max_salary != null
      ? `$${fmt(job.min_salary)} – $${fmt(job.max_salary)}`
      : `$${fmt(job.min_salary ?? job.max_salary!)}`
  const period = job.salary_period === 'Hourly' ? 'per hour' : job.salary_period === 'Salary' ? 'per year' : ''
  return [range, period].filter(Boolean).join(' ')
}

/** The site's root ('/') — a candidate's default landing page, whether they
 * typed the domain directly or clicked a generic "see our openings" link
 * (as opposed to /apply/job/:jobId, which a specific job board posting
 * links straight to, bypassing this page entirely). Organization
 * name/logo (GET /api/public/organization[/logo]) plus every open job
 * (GET /api/public/jobs) - see routes/public.py for why these are a
 * separate, minimal public contract rather than reusing the
 * recruiter-side /api/organization or Job.to_dict(). */
export function CareersLandingPage() {
  const [org, setOrg] = useState<PublicOrganizationInfo | null>(null)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  const [jobs, setJobs] = useState<PublicJobSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null

    Promise.all([publicApplyApi.getOrganization(), publicApplyApi.listJobs()])
      .then(([orgData, jobsData]) => {
        if (cancelled) return
        setOrg(orgData)
        setJobs(jobsData)
        if (orgData.has_logo) {
          publicApplyApi
            .getOrganizationLogo()
            .then((blob) => {
              if (cancelled) return
              objectUrl = URL.createObjectURL(blob)
              setLogoUrl(objectUrl)
            })
            .catch(() => {
              // A missing/broken logo shouldn't block the rest of the page -
              // it just renders without one.
            })
        }
      })
      .catch((err) => {
        if (!cancelled) setError(publicErrorMessage(err, 'Something went wrong loading this page.'))
      })

    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [])

  if (error) {
    return (
      <div className="public-page">
        <div className="card public-card">
          <p className="error-banner">{error}</p>
        </div>
      </div>
    )
  }

  if (!org || !jobs) return <div className="page-loading">Loading…</div>

  return (
    <div className="landing-page">
      <header className="landing-header">
        {logoUrl && <img src={logoUrl} alt={org.name} className="landing-logo" />}
        <h1>{org.name}</h1>
        <p className="subtle">Current openings</p>
      </header>

      {jobs.length === 0 ? (
        <p className="subtle landing-empty">No open positions right now — please check back soon.</p>
      ) : (
        <div className="landing-jobs-list">
          {jobs.map((job) => {
            const compensation = formatCompensation(job)
            return (
              <Link key={job.id} to={`/apply/job/${job.id}`} className="card landing-job-card">
                <h2>{job.title}</h2>
                <div className="landing-job-meta">
                  {job.location && <span>{job.location}</span>}
                  {job.job_type.length > 0 && <span>{job.job_type.join(', ')}</span>}
                  {compensation && <span>{compensation}</span>}
                </div>
              </Link>
            )
          })}
        </div>
      )}

      <footer className="landing-footer">
        <Link to="/status">Already applied? Check your status</Link>
      </footer>
    </div>
  )
}

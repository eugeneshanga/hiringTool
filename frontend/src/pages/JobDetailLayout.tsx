import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
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
  const [error, setError] = useState<string | null>(null)

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
      <div className="job-detail-header">
        <Link to="/jobs" className="link-button">
          ‹ Back
        </Link>
        <h1>{job.title}</h1>
        {job.location && <p className="subtle">{job.location}</p>}
      </div>
      <div className="job-detail-body">
        <aside className="job-detail-sidebar">
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
          <Outlet context={{ job, reloadJob: load } satisfies JobDetailContext} />
        </div>
      </div>
    </div>
  )
}

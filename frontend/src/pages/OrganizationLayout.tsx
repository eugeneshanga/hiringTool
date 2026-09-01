import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useOutletContext } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Organization } from '../api/types'

export interface OrganizationContext {
  organization: Organization
  reloadOrganization: () => Promise<void>
}

export function useOrganizationContext() {
  return useOutletContext<OrganizationContext>()
}

/** "Manage organization" (admin-only, linked from the header's account
 * dropdown): a sidebar of settings areas, same layout pattern as the
 * meeting-stage editor's Stage editor sidebar (StageEditorLayout.tsx). */
export function OrganizationLayout() {
  const [organization, setOrganization] = useState<Organization | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setOrganization(await api.getOrganization())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load organization')
    }
  }, [])

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

  if (!organization) {
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
          <Link to="/dashboard" className="link-button back-link">
            ‹ Back
          </Link>
          <div className="org-sidebar-identity">
            <span className="org-sidebar-logo" aria-hidden="true">
              {organization.name.slice(0, 2).toUpperCase()}
            </span>
            <strong>{organization.name}</strong>
          </div>
          <NavLink to="/organization" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Organization
          </NavLink>
          <NavLink to="/organization/users" className={({ isActive }) => (isActive ? 'active' : '')}>
            Users &amp; licenses
          </NavLink>
          <NavLink to="/organization/blocklist" className={({ isActive }) => (isActive ? 'active' : '')}>
            Blocklist
          </NavLink>
        </aside>
        <div className="job-detail-content">
          <Outlet context={{ organization, reloadOrganization: load } satisfies OrganizationContext} />
        </div>
      </div>
    </div>
  )
}

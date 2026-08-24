import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { Organization } from '../api/types'

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const first = parts[0]?.[0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

/** The account dropdown in the header: who's logged in, the organization
 * identity, and account-level actions. "Manage organization" only shows for
 * admins (the page itself is also gated - see AdminRoute.tsx - this just
 * avoids offering a link that 403s). "Update profile" and "Log out" are
 * fully wired for everyone. */
export function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const [organization, setOrganization] = useState<Organization | null>(null)
  const [logoUrl, setLogoUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!open || organization) return
    api
      .getOrganization()
      .then((org) => {
        setOrganization(org)
        if (org.has_logo) {
          api
            .downloadOrganizationLogo()
            .then(({ blob }) => setLogoUrl(URL.createObjectURL(blob)))
            .catch(() => setLogoUrl(null))
        }
      })
      .catch(() => setOrganization(null))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    return () => {
      if (logoUrl) URL.revokeObjectURL(logoUrl)
    }
  }, [logoUrl])

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!user) return null

  return (
    <div className="user-menu" ref={ref}>
      <button
        type="button"
        className="user-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="user-avatar" aria-hidden="true">
          {initials(user.name)}
        </span>
        <span className="user-menu-name">{user.name}</span>
        <span className="user-menu-caret" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div className="user-menu-list" role="menu">
          {organization && (
            <>
              <div className="user-menu-section-label">Organization</div>
              <div className="user-menu-org-row">
                {logoUrl ? (
                  <img className="user-menu-org-logo" src={logoUrl} alt="" />
                ) : (
                  <span className="user-menu-org-logo" aria-hidden="true">
                    {initials(organization.name)}
                  </span>
                )}
                <span className="user-menu-org-name">{organization.name}</span>
              </div>

              <div className="user-menu-divider" />
            </>
          )}

          <button
            type="button"
            role="menuitem"
            className="user-menu-item"
            onClick={() => {
              setOpen(false)
              navigate('/profile')
            }}
          >
            Update profile
          </button>
          {user.role === 'admin' && (
            <button
              type="button"
              role="menuitem"
              className="user-menu-item"
              onClick={() => {
                setOpen(false)
                navigate('/organization')
              }}
            >
              Manage organization
            </button>
          )}
          <button
            type="button"
            role="menuitem"
            className="user-menu-item"
            onClick={() => {
              setOpen(false)
              logout()
            }}
          >
            Log out
          </button>
        </div>
      )}
    </div>
  )
}

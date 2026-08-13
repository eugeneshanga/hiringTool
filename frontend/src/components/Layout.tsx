import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="brand">HiringTool</span>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Home
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => (isActive ? 'active' : '')}>
            Jobs
          </NavLink>
          <NavLink to="/candidates" className={({ isActive }) => (isActive ? 'active' : '')}>
            Candidates
          </NavLink>
        </nav>
        <div className="user-info">
          <span>
            {user?.name} <span className="role-badge">{user?.role}</span>
          </span>
          <button onClick={logout} className="link-button">
            Log out
          </button>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  )
}

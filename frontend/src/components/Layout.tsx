import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { UserMenu } from './UserMenu'

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          HiringTool
        </Link>
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
        <UserMenu />
      </header>
      <main className="app-main">{children}</main>
    </div>
  )
}

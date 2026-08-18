import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useCandidateAuth } from '../candidateAuth/CandidateAuthContext'

/** Shell for candidate-facing pages — deliberately no nav links yet beyond
 * Home, since browsing/applying to jobs is future work (see CandidateHomePage). */
export function CandidateLayout({ children }: { children: ReactNode }) {
  const { candidate, logout } = useCandidateAuth()

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/apply" className="brand">
          HiringTool
        </Link>
        <nav />
        <div className="user-info">
          <span>{candidate?.name}</span>
          <button onClick={logout} className="link-button">
            Log out
          </button>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  )
}

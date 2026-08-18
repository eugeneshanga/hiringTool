import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useCandidateAuth } from '../candidateAuth/CandidateAuthContext'

export function CandidateProtectedRoute({ children }: { children: ReactNode }) {
  const { candidate, loading } = useCandidateAuth()

  if (loading) return <div className="page-loading">Loading…</div>
  if (!candidate) return <Navigate to="/apply/login" replace />
  return <>{children}</>
}

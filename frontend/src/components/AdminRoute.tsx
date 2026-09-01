import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/** Like ProtectedRoute, but also requires role === 'admin' - used for the
 * "Manage organization" area. Sits inside ProtectedRoute (App.tsx), so
 * `loading`/`user` are already resolved by the time this renders; a
 * non-admin just bounces to the recruiter dashboard rather than seeing an
 * error. */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  if (user?.role !== 'admin') return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

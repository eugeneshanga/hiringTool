import type { ReactNode } from 'react'
import { PublicHeader } from './PublicHeader'

/** Wraps every public-facing route (landing, apply, schedule, status) with
 * the shared top bar - see PublicHeader. Applied per-route in App.tsx, the
 * same pattern Layout.tsx uses for the recruiter-authenticated shell -
 * rather than each page rendering PublicHeader itself, since several of
 * these pages have multiple early-return branches (loading/error/success)
 * and wrapping once at the route level means the header can't accidentally
 * get left out of one of them. */
export function PublicPageLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <PublicHeader />
      {children}
    </>
  )
}

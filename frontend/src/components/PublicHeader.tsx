import { Link } from 'react-router-dom'
import { useOrganizationBranding } from '../hooks/useOrganizationBranding'

/** The persistent top bar every public-facing page shares (the careers
 * landing page, the apply/schedule/status flow) - distinct from Layout.tsx,
 * which is the recruiter-authenticated app's own header/nav. Always links
 * back to "/" (the landing page), so a candidate mid-flow can get back to
 * the full job list at any point. */
export function PublicHeader() {
  const { name, logoUrl } = useOrganizationBranding()

  return (
    <header className="public-topbar">
      <Link to="/" className="public-topbar-brand">
        {logoUrl && <img src={logoUrl} alt="" className="public-topbar-logo" />}
        <span>{name}</span>
      </Link>
    </header>
  )
}

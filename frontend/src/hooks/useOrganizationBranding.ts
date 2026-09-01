import { useEffect, useState } from 'react'
import { publicApplyApi } from '../api/publicApplyClient'

interface OrganizationBranding {
  name: string
  logoUrl: string | null
  loaded: boolean
}

/** Fetches the org's public name + logo (see routes/public.py) and hands
 * back an object-URL for the logo - shared by PublicHeader (every public
 * page's persistent top bar) and CareersLandingPage (which shows the same
 * logo again, larger, in its own hero), so the fetch-and-object-URL-
 * lifecycle code lives in exactly one place rather than being copied
 * between them. Each caller still fetches independently (no shared cache
 * across component instances) - on the landing page specifically, that's
 * two small GETs instead of one, which is a fine trade for not needing a
 * context provider just for this. */
export function useOrganizationBranding(): OrganizationBranding {
  const [name, setName] = useState('')
  const [logoUrl, setLogoUrl] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    publicApplyApi
      .getOrganization()
      .then((org) => {
        if (cancelled) return
        setName(org.name)
        if (org.has_logo) {
          publicApplyApi
            .getOrganizationLogo()
            .then((blob) => {
              if (cancelled) return
              objectUrl = URL.createObjectURL(blob)
              setLogoUrl(objectUrl)
            })
            .catch(() => {
              // A missing/broken logo shouldn't block anything - just no image.
            })
        }
      })
      .catch(() => {
        // Org info failing shouldn't break the page either - name just stays empty.
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [])

  return { name, logoUrl, loaded }
}

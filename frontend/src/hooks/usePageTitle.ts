import { useEffect } from 'react'

/** Sets the browser tab title for the page that calls it. Without this,
 * every page just kept whatever the last one set (or, before any page had,
 * index.html's static fallback) - which is how this whole site ended up
 * showing the literal word "frontend" in every tab (Vite's scaffolded
 * default title, never customized). Pass the full title you want shown,
 * already including whatever suffix/branding makes sense for that page -
 * this hook doesn't add one itself, since "HiringTool" (the internal tool)
 * and the organization's real name (the public careers site) are two
 * different brands depending on which side of the app is calling it. */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title
  }, [title])
}

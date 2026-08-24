export const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:5050'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** Builds the token storage + fetch plumbing for one auth boundary, scoped to
 * a single localStorage key. client.ts and candidateClient.ts each call this
 * with their own key to get their own instance — recruiter and candidate
 * sessions stay independent (a recruiter and a candidate can be logged in in
 * the same browser at once without clobbering each other) even though the
 * request/token mechanics are shared. The backend enforces the actual
 * boundary between them (see app.py's token_verification_loader); this only
 * shares the plumbing, not the sessions. */
export function createApiClient(tokenKey: string) {
  function getToken(): string | null {
    return localStorage.getItem(tokenKey)
  }

  function setToken(token: string | null) {
    if (token) localStorage.setItem(tokenKey, token)
    else localStorage.removeItem(tokenKey)
  }

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = getToken()
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> | undefined),
    }
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })

    if (res.status === 204) return undefined as T

    const isJson = res.headers.get('content-type')?.includes('application/json')
    const body = isJson ? await res.json() : undefined

    if (!res.ok) {
      throw new ApiError(res.status, body?.error ?? `Request failed (${res.status})`)
    }
    return body as T
  }

  /** Like `request`, but for multipart file uploads — no Content-Type header,
   * so the browser can set it (with the multipart boundary) itself. */
  async function requestForm<T>(path: string, formData: FormData): Promise<T> {
    const token = getToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', headers, body: formData })
    const isJson = res.headers.get('content-type')?.includes('application/json')
    const body = isJson ? await res.json() : undefined

    if (!res.ok) {
      throw new ApiError(res.status, body?.error ?? `Request failed (${res.status})`)
    }
    return body as T
  }

  /** Fetches a file with the auth header attached (plain <a href> downloads
   * can't carry it) and returns it with whatever filename the server suggested. */
  async function requestBlob(path: string): Promise<{ blob: Blob; filename: string | null }> {
    const token = getToken()
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`

    const res = await fetch(`${BASE_URL}${path}`, { headers })
    if (!res.ok) {
      let message = `Request failed (${res.status})`
      const isJson = res.headers.get('content-type')?.includes('application/json')
      if (isJson) {
        const body = await res.json()
        message = body?.error ?? message
      }
      throw new ApiError(res.status, message)
    }

    const disposition = res.headers.get('content-disposition') ?? ''
    const match = /filename="?([^";]+)"?/.exec(disposition)
    const filename = match ? decodeURIComponent(match[1]) : null
    return { blob: await res.blob(), filename }
  }

  return { getToken, setToken, request, requestForm, requestBlob }
}

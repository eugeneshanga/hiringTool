import { ApiError, BASE_URL } from './httpClient'
import type { ApplicationStatus, BookingConfirmation, PublicApplication, PublicJob } from './types'

// No auth at all — every route here is public (backend/routes/apply.py,
// routes/status.py). A small dedicated client rather than reusing
// createApiClient (client.ts/candidateClient.ts): those always attach a
// bearer token from localStorage, which has no meaning here.
async function publicRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers as Record<string, string> | undefined) },
  })

  const isJson = res.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await res.json() : undefined

  if (!res.ok) {
    throw new ApiError(res.status, body?.error ?? `Request failed (${res.status})`)
  }
  return body as T
}

/** Like publicRequest, but for the multipart submission POST /api/apply now
 * requires (it carries a resume file) — no Content-Type header, so the
 * browser sets it itself with the correct multipart boundary. Mirrors
 * httpClient.ts's requestForm. */
async function publicRequestForm<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', body: formData })

  const isJson = res.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await res.json() : undefined

  if (!res.ok) {
    throw new ApiError(res.status, body?.error ?? `Request failed (${res.status})`)
  }
  return body as T
}

export interface ApplyFormInput {
  first_name: string
  last_name: string
  email: string
  phone?: string
  address_line1?: string
  city?: string
  state?: string
  postal_code?: string
  job_id: number
  resume: File
  // 'yes' | 'no' - see routes/apply.py's _parse_required_yes_no. Both required.
  work_authorized: 'yes' | 'no'
  requires_visa_sponsorship: 'yes' | 'no'
  // Honeypot — see PublicApplyPage. Always empty for a real person; the
  // backend blends a non-empty value into a normal-looking success response
  // rather than erroring, so there's nothing to distinguish here either.
  website?: string
}

export const publicApplyApi = {
  getJob: (jobId: number) => publicRequest<PublicJob>(`/api/apply/jobs/${jobId}`),

  apply: (data: ApplyFormInput) => {
    const form = new FormData()
    for (const [key, value] of Object.entries(data)) {
      if (value !== undefined && value !== '') form.append(key, value as string | Blob)
    }
    return publicRequestForm<{ status: string }>('/api/apply', form)
  },

  getApplication: (token: string) => publicRequest<PublicApplication>(`/api/apply/${encodeURIComponent(token)}`),

  submitApplication: (
    token: string,
    data: { answers: { question_id: number; answer_text: string }[]; slot_start: string; slot_end: string },
  ) =>
    publicRequest<BookingConfirmation>(`/api/apply/${encodeURIComponent(token)}/submit`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getStatus: (params: { code?: string; phone?: string }) => {
    const qs = new URLSearchParams()
    if (params.code) qs.set('code', params.code)
    if (params.phone) qs.set('phone', params.phone)
    return publicRequest<ApplicationStatus>(`/api/status?${qs.toString()}`)
  },
}

/** Every public-apply page needs the same "what do I show the user" mapping
 * from a thrown error — pulled out so all three agree, and so a 429 (the
 * anti-abuse rate limits on POST /api/apply and GET /api/status - see their
 * backend docstrings) reads as "slow down", not Flask-Limiter's raw default
 * response, which isn't even guaranteed to be JSON. */
export function publicErrorMessage(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return "You've hit a rate limit — please wait a bit and try again."
    return err.message
  }
  return fallback
}

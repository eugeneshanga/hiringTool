import { ApiError, BASE_URL } from './httpClient'
import type {
  ApplicationStatus,
  BookingConfirmation,
  CandidateDocumentSubmission,
  PublicApplication,
  PublicJob,
  PublicJobSummary,
  PublicOrganizationInfo,
} from './types'

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

/** Like publicRequest, but for a raw file (the landing page's organization
 * logo) rather than JSON - mirrors httpClient.ts's requestBlob, minus the
 * auth header (nothing here needs one - see routes/public.py). */
async function publicRequestBlob(path: string): Promise<Blob> {
  const res = await fetch(`${BASE_URL}${path}`)
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    if (res.headers.get('content-type')?.includes('application/json')) {
      const body = await res.json()
      message = body?.error ?? message
    }
    throw new ApiError(res.status, message)
  }
  return res.blob()
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
  // The job's screening questions, answered here - see routes/apply.py's
  // apply() for how qualification gets evaluated right after this submits.
  // Sent as a JSON string field (not nested FormData entries - multipart
  // has no native array/object representation), so the backend parses it
  // back out with json.loads.
  answers: { question_id: number; answer_text: string }[]
  // Honeypot — see PublicApplyPage. Always empty for a real person; the
  // backend blends a non-empty value into a normal-looking success response
  // rather than erroring, so there's nothing to distinguish here either.
  website?: string
}

export const publicApplyApi = {
  getJob: (jobId: number) => publicRequest<PublicJob>(`/api/apply/jobs/${jobId}`),

  getOrganization: () => publicRequest<PublicOrganizationInfo>('/api/public/organization'),

  getOrganizationLogo: () => publicRequestBlob('/api/public/organization/logo'),

  listJobs: () => publicRequest<PublicJobSummary[]>('/api/public/jobs'),

  apply: (data: ApplyFormInput) => {
    const form = new FormData()
    for (const [key, value] of Object.entries(data)) {
      if (value === undefined || value === '') continue
      form.append(key, key === 'answers' ? JSON.stringify(value) : (value as string | Blob))
    }
    return publicRequestForm<{ status: string }>('/api/apply', form)
  },

  getApplication: (token: string) => publicRequest<PublicApplication>(`/api/apply/${encodeURIComponent(token)}`),

  submitApplication: (token: string, data: { slot_start: string; slot_end: string }) =>
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

  // Same code-or-phone identification as getStatus - a candidate re-sends
  // whichever one they originally looked up with, alongside the file. See
  // routes/status.py for the type/size validation this goes through.
  uploadStatusDocument: (params: { code?: string; phone?: string }, onboardingItemId: number, file: File) => {
    const form = new FormData()
    if (params.code) form.append('code', params.code)
    if (params.phone) form.append('phone', params.phone)
    form.append('onboarding_item_id', String(onboardingItemId))
    form.append('file', file)
    return publicRequestForm<CandidateDocumentSubmission>('/api/status/documents', form)
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

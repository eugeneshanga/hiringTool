import type {
  AvailableMeetingStage,
  Candidate,
  CandidateDetail,
  CandidateDocumentChecklistItem,
  CandidateDocumentSubmission,
  CandidateDocumentType,
  Interview,
  Job,
  ScreeningQuestion,
  MeetingStageTemplate,
  StageProgressStatus,
  User,
} from './types'

export interface ScreeningQuestionInput {
  question_text: string
  question_label?: string | null
  answer_options?: string[]
  qualified_answers?: string[]
}

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:5050'
const TOKEN_KEY = 'hiringtool_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
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

/** Saves a blob to disk via a throwaway link click — the standard way to
 * trigger a browser "Save As" for content fetched via JS rather than a URL. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** Opens a blob in a new tab (for "view" rather than "download" links). */
export function openBlob(blob: Blob) {
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export const api = {
  register: (data: { first_name: string; last_name: string; email: string; phone?: string; password: string }) =>
    request<{ access_token: string; user: User }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>('/api/auth/me'),

  listJobs: (params?: { status?: string; search?: string }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set('status', params.status)
    if (params?.search) qs.set('search', params.search)
    const s = qs.toString()
    return request<Job[]>(`/api/jobs${s ? `?${s}` : ''}`)
  },
  getJob: (id: number) => request<Job>(`/api/jobs/${id}`),
  createJob: (data: Partial<Job>) =>
    request<Job>('/api/jobs', { method: 'POST', body: JSON.stringify(data) }),
  updateJob: (id: number, data: Partial<Job>) =>
    request<Job>(`/api/jobs/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteJob: (id: number) => request<void>(`/api/jobs/${id}`, { method: 'DELETE' }),

  listMeetingStages: (jobId: number) =>
    request<MeetingStageTemplate[]>(`/api/jobs/${jobId}/meeting-stages`),
  getMeetingStage: (jobId: number, templateId: number) =>
    request<MeetingStageTemplate>(`/api/jobs/${jobId}/meeting-stages/${templateId}`),
  listAvailableMeetingStages: (jobId: number) =>
    request<AvailableMeetingStage[]>(`/api/jobs/${jobId}/meeting-stages/available`),
  createMeetingStage: (
    jobId: number,
    data: {
      meeting_type: string
      stage_name: string
      duration_minutes?: number | null
      default_capacity?: number | null
      location?: string | null
      instructions?: string | null
    },
  ) =>
    request<MeetingStageTemplate>(`/api/jobs/${jobId}/meeting-stages`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateMeetingStage: (
    jobId: number,
    templateId: number,
    data: {
      meeting_type?: string
      stage_name?: string
      duration_minutes?: number | null
      default_capacity?: number | null
      location?: string | null
      instructions?: string | null
      scheduling_window_days?: number
    },
  ) =>
    request<MeetingStageTemplate>(`/api/jobs/${jobId}/meeting-stages/${templateId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  moveMeetingStage: (jobId: number, templateId: number, direction: 'up' | 'down') =>
    request<MeetingStageTemplate[]>(`/api/jobs/${jobId}/meeting-stages/${templateId}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ direction }),
    }),
  deleteMeetingStage: (jobId: number, templateId: number) =>
    request<void>(`/api/jobs/${jobId}/meeting-stages/${templateId}`, { method: 'DELETE' }),

  listCandidates: (params?: { search?: string; stage?: string; job_id?: number }) => {
    const qs = new URLSearchParams()
    if (params?.search) qs.set('search', params.search)
    if (params?.stage) qs.set('stage', params.stage)
    if (params?.job_id) qs.set('job_id', String(params.job_id))
    const s = qs.toString()
    return request<Candidate[]>(`/api/candidates${s ? `?${s}` : ''}`)
  },
  getCandidate: (id: number) => request<CandidateDetail>(`/api/candidates/${id}`),
  createCandidate: (data: Partial<Candidate>) =>
    request<Candidate>('/api/candidates', { method: 'POST', body: JSON.stringify(data) }),
  updateCandidate: (id: number, data: Partial<Candidate>) =>
    request<CandidateDetail>(`/api/candidates/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteCandidate: (id: number) => request<void>(`/api/candidates/${id}`, { method: 'DELETE' }),

  uploadResume: (candidateId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return requestForm<CandidateDetail>(`/api/candidates/${candidateId}/resume`, form)
  },
  downloadResume: (candidateId: number) => requestBlob(`/api/candidates/${candidateId}/resume`),

  listDocumentChecklist: (candidateId: number) =>
    request<CandidateDocumentChecklistItem[]>(`/api/candidates/${candidateId}/documents`),
  uploadDocument: (candidateId: number, docType: CandidateDocumentType, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return requestForm<CandidateDocumentSubmission>(
      `/api/candidates/${candidateId}/documents/${docType}`,
      form,
    )
  },
  downloadDocument: (candidateId: number, docType: CandidateDocumentType) =>
    requestBlob(`/api/candidates/${candidateId}/documents/${docType}`),
  downloadAllDocuments: (candidateId: number) =>
    requestBlob(`/api/candidates/${candidateId}/documents/download-all`),

  updateScreeningAnswers: (
    candidateId: number,
    answers: { question_id: number; answer_text: string }[],
  ) =>
    request<CandidateDetail>(`/api/candidates/${candidateId}/screening-answers`, {
      method: 'PUT',
      body: JSON.stringify({ answers }),
    }),

  updateStageProgress: (
    candidateId: number,
    templateId: number,
    data: {
      status?: StageProgressStatus
      scheduled_at?: string | null
      location?: string | null
      notes?: string | null
      score_communication?: number | null
      score_energy?: number | null
      score_relevant_experience?: number | null
    },
  ) =>
    request<CandidateDetail>(`/api/candidates/${candidateId}/stages/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  listStageScreeningQuestions: (jobId: number, templateId: number) =>
    request<ScreeningQuestion[]>(`/api/jobs/${jobId}/meeting-stages/${templateId}/screening-questions`),
  createStageScreeningQuestion: (jobId: number, templateId: number, data: ScreeningQuestionInput) =>
    request<ScreeningQuestion>(`/api/jobs/${jobId}/meeting-stages/${templateId}/screening-questions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateStageScreeningQuestion: (
    jobId: number,
    templateId: number,
    questionId: number,
    data: ScreeningQuestionInput,
  ) =>
    request<ScreeningQuestion>(
      `/api/jobs/${jobId}/meeting-stages/${templateId}/screening-questions/${questionId}`,
      { method: 'PATCH', body: JSON.stringify(data) },
    ),
  deleteStageScreeningQuestion: (jobId: number, templateId: number, questionId: number) =>
    request<void>(
      `/api/jobs/${jobId}/meeting-stages/${templateId}/screening-questions/${questionId}`,
      { method: 'DELETE' },
    ),

  listInterviews: (params?: { upcoming?: boolean; job_id?: number }) => {
    const qs = new URLSearchParams()
    if (params?.upcoming) qs.set('upcoming', 'true')
    if (params?.job_id) qs.set('job_id', String(params.job_id))
    const s = qs.toString()
    return request<Interview[]>(`/api/interviews${s ? `?${s}` : ''}`)
  },
  createInterview: (data: Partial<Interview>) =>
    request<Interview>('/api/interviews', { method: 'POST', body: JSON.stringify(data) }),
  updateInterview: (id: number, data: Partial<Interview>) =>
    request<Interview>(`/api/interviews/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteInterview: (id: number) => request<void>(`/api/interviews/${id}`, { method: 'DELETE' }),
  enrollCandidate: (id: number, candidateId: number) =>
    request<Interview>(`/api/interviews/${id}/enroll`, {
      method: 'POST',
      body: JSON.stringify({ candidate_id: candidateId }),
    }),
  unenrollCandidate: (id: number, candidateId: number) =>
    request<Interview>(`/api/interviews/${id}/unenroll`, {
      method: 'POST',
      body: JSON.stringify({ candidate_id: candidateId }),
    }),
}

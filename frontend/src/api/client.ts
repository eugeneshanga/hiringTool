import type { Candidate, Interview, Job, User } from './types'

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

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>('/api/auth/me'),

  listJobs: (params?: { status?: string }) => {
    const qs = params?.status ? `?status=${encodeURIComponent(params.status)}` : ''
    return request<Job[]>(`/api/jobs${qs}`)
  },
  createJob: (data: Partial<Job>) =>
    request<Job>('/api/jobs', { method: 'POST', body: JSON.stringify(data) }),
  updateJob: (id: number, data: Partial<Job>) =>
    request<Job>(`/api/jobs/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteJob: (id: number) => request<void>(`/api/jobs/${id}`, { method: 'DELETE' }),

  listCandidates: (params?: { search?: string; stage?: string; job_id?: number }) => {
    const qs = new URLSearchParams()
    if (params?.search) qs.set('search', params.search)
    if (params?.stage) qs.set('stage', params.stage)
    if (params?.job_id) qs.set('job_id', String(params.job_id))
    const s = qs.toString()
    return request<Candidate[]>(`/api/candidates${s ? `?${s}` : ''}`)
  },
  createCandidate: (data: Partial<Candidate>) =>
    request<Candidate>('/api/candidates', { method: 'POST', body: JSON.stringify(data) }),
  updateCandidate: (id: number, data: Partial<Candidate>) =>
    request<Candidate>(`/api/candidates/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteCandidate: (id: number) => request<void>(`/api/candidates/${id}`, { method: 'DELETE' }),

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

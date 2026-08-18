import { ApiError } from './client'
import type { CandidateAccount } from './types'

// Deliberately separate from client.ts's token storage/request helper: a
// candidate and a recruiter can be logged in at the same time in the same
// browser (e.g. one tab testing each side) without clobbering each other,
// since each keeps its own token under its own key. The backend enforces the
// matching boundary — see app.py's token_verification_loader.
const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:5050'
const TOKEN_KEY = 'hiringtool_candidate_token'

export function getCandidateToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setCandidateToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getCandidateToken()
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

export const candidateApi = {
  register: (data: { first_name: string; last_name: string; email: string; phone?: string; password: string }) =>
    request<{ access_token: string; candidate: CandidateAccount }>('/api/candidate-auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string; candidate: CandidateAccount }>('/api/candidate-auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<CandidateAccount>('/api/candidate/me'),
}

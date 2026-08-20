import { createApiClient } from './httpClient'
import type { CandidateAccount } from './types'

// Deliberately separate from client.ts's token storage: a candidate and a
// recruiter can be logged in at the same time in the same browser (e.g. one
// tab testing each side) without clobbering each other, since each keeps its
// own token under its own key. The backend enforces the matching boundary —
// see app.py's token_verification_loader. The request/token *mechanics* are
// shared via createApiClient (see httpClient.ts); only the session itself is
// kept separate.
const TOKEN_KEY = 'hiringtool_candidate_token'

const { getToken: getCandidateToken, setToken: setCandidateToken, request } = createApiClient(TOKEN_KEY)
export { getCandidateToken, setCandidateToken }

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

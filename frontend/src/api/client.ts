import type {
  AvailableMeetingStage,
  BlocklistEntry,
  BlocklistEntryType,
  Candidate,
  CandidateDetail,
  CandidateDocumentChecklistItem,
  CandidateDocumentSubmission,
  GoogleCalendarStatus,
  Interview,
  Job,
  Organization,
  OnboardingDocumentItem,
  OnboardingItemType,
  ScreeningQuestion,
  MeetingStageTemplate,
  StageProgressStatus,
  User,
  UserRole,
} from './types'
import { BASE_URL, createApiClient } from './httpClient'

export { ApiError } from './httpClient'

export interface ScreeningQuestionInput {
  question_text: string
  question_label?: string | null
  answer_options?: string[]
  qualified_answers?: string[]
}

export interface OnboardingItemInput {
  description: string
  type?: OnboardingItemType
  required?: boolean
}

const TOKEN_KEY = 'hiringtool_token'

const { getToken, setToken, request, requestForm, requestBlob } = createApiClient(TOKEN_KEY)
export { getToken, setToken }

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
  updateProfile: (data: { first_name?: string; last_name?: string; phone?: string | null }) =>
    request<User>('/api/auth/me', { method: 'PATCH', body: JSON.stringify(data) }),

  // Google Calendar connect is a real top-level navigation (Google's own
  // redirect back to /callback only works that way), not a fetch - the
  // frontend just needs the fully-formed URL, token included as a query
  // param since a page navigation carries no Authorization header. See
  // calendar_auth.py's google_connect() docstring.
  googleCalendarConnectUrl: () =>
    `${BASE_URL}/api/auth/google/connect?jwt=${encodeURIComponent(getToken() ?? '')}`,
  getGoogleCalendarStatus: () => request<GoogleCalendarStatus>('/api/auth/google/status'),
  disconnectGoogleCalendar: () => request<void>('/api/auth/google/disconnect', { method: 'DELETE' }),

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
  uploadDocument: (candidateId: number, itemId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return requestForm<CandidateDocumentSubmission>(
      `/api/candidates/${candidateId}/documents/${itemId}`,
      form,
    )
  },
  downloadDocument: (candidateId: number, itemId: number) =>
    requestBlob(`/api/candidates/${candidateId}/documents/${itemId}`),
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
      cancellation_reason?: string | null
      prompt_reschedule?: boolean | null
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

  listStageOnboardingItems: (jobId: number, templateId: number) =>
    request<OnboardingDocumentItem[]>(`/api/jobs/${jobId}/meeting-stages/${templateId}/onboarding-items`),
  createStageOnboardingItem: (jobId: number, templateId: number, data: OnboardingItemInput) =>
    request<OnboardingDocumentItem>(`/api/jobs/${jobId}/meeting-stages/${templateId}/onboarding-items`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateStageOnboardingItem: (
    jobId: number,
    templateId: number,
    itemId: number,
    data: OnboardingItemInput,
  ) =>
    request<OnboardingDocumentItem>(
      `/api/jobs/${jobId}/meeting-stages/${templateId}/onboarding-items/${itemId}`,
      { method: 'PATCH', body: JSON.stringify(data) },
    ),
  deleteStageOnboardingItem: (jobId: number, templateId: number, itemId: number) =>
    request<void>(
      `/api/jobs/${jobId}/meeting-stages/${templateId}/onboarding-items/${itemId}`,
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

  // --- Organization (name, logo, banner) - GET is any recruiter, editing is
  // admin-only (enforced server-side; the frontend also hides the nav entry
  // for non-admins - see AdminRoute.tsx). ---
  getOrganization: () => request<Organization>('/api/organization'),
  updateOrganization: (data: { name?: string }) =>
    request<Organization>('/api/organization', { method: 'PATCH', body: JSON.stringify(data) }),
  uploadOrganizationLogo: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return requestForm<Organization>('/api/organization/logo', form)
  },
  downloadOrganizationLogo: () => requestBlob('/api/organization/logo'),
  deleteOrganizationLogo: () => request<Organization>('/api/organization/logo', { method: 'DELETE' }),
  uploadOrganizationBanner: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return requestForm<Organization>('/api/organization/banner', form)
  },
  downloadOrganizationBanner: () => requestBlob('/api/organization/banner'),
  deleteOrganizationBanner: () => request<Organization>('/api/organization/banner', { method: 'DELETE' }),

  // --- Users & licenses (admin-only) ---
  listOrgUsers: () => request<User[]>('/api/organization/users'),
  createOrgUser: (data: {
    first_name: string
    last_name: string
    email: string
    phone?: string | null
    password: string
    role: UserRole
  }) => request<User>('/api/organization/users', { method: 'POST', body: JSON.stringify(data) }),
  updateOrgUser: (id: number, data: { role?: UserRole; is_active?: boolean }) =>
    request<User>(`/api/organization/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  setOrgUserPassword: (id: number, password: string) =>
    request<User>(`/api/organization/users/${id}/set-password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  // --- Blocklist (admin-only) ---
  listBlocklist: () => request<BlocklistEntry[]>('/api/organization/blocklist'),
  createBlocklistEntry: (data: { type: BlocklistEntryType; value: string; reason?: string | null }) =>
    request<BlocklistEntry>('/api/organization/blocklist', { method: 'POST', body: JSON.stringify(data) }),
  deleteBlocklistEntry: (id: number) =>
    request<void>(`/api/organization/blocklist/${id}`, { method: 'DELETE' }),
}

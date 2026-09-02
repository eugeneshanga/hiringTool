export type Stage = 'Applied' | 'Interview' | 'Offer' | 'Hired' | 'Rejected'
export type JobStatus = 'Published' | 'Draft' | 'Closed'
export type JobType = 'Full-time' | 'Part-time' | 'Remote'
export type SalaryPeriod = 'Hourly' | 'Salary'
export type MeetingType = 'Interview' | 'Orientation' | 'Other'
// The meeting stage template's own type vocabulary — distinct from MeetingType above,
// which is what an actual scheduled Interview uses.
export type StageMeetingType =
  | 'Virtual interview'
  | 'In-person interview'
  | 'In-person orientation'
  | 'Instant meeting link'

export type UserRole = 'admin' | 'recruiter' | 'interviewer'

export interface User {
  id: number
  first_name: string
  last_name: string
  name: string
  phone: string | null
  // This interviewer's own static video-meeting link (RingCentral) - shown
  // to candidates in booking confirmations once they're assigned as an
  // interviewer for a stage. See ProfilePage.tsx.
  personal_meeting_link: string | null
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
}

// A recruiter/interviewer's connected Microsoft/Outlook Calendar (see
// microsoft_calendar.py and routes/calendar_auth.py) - not to be confused
// with Candidate, which is the per-job application/pipeline record.
export interface MicrosoftCalendarStatus {
  connected: boolean
  account_email?: string
}

// This single-tenant app's one Organization row - name plus whether a
// logo/banner is set (the images themselves are fetched separately as blobs
// via GET /api/organization/logo|banner, same pattern as candidate
// documents, so they can carry an auth header).
export interface Organization {
  id: number
  name: string
  has_logo: boolean
  has_banner: boolean
  // Bounds the public apply flow's candidate-visible scheduling
  // availability (see microsoft_calendar.get_free_slots) - editable from the
  // Organization Settings page. scheduling_days is a list of
  // date.weekday() ints, Monday=0 .. Sunday=6.
  scheduling_timezone: string
  scheduling_working_hours_start: number
  scheduling_working_hours_end: number
  scheduling_days: number[]
}

export type BlocklistEntryType = 'email' | 'domain'

export interface BlocklistEntry {
  id: number
  type: BlocklistEntryType
  value: string
  reason: string | null
  created_at: string
}

export interface MeetingStageTemplate {
  id: number
  job_id: number
  meeting_type: StageMeetingType
  stage_name: string
  duration_minutes: number | null
  // Only meaningful for 'In-person orientation' - a default that pre-fills
  // a new session's capacity, not an enforced cap (see models.py).
  default_capacity: number | null
  // Only meaningful for the two in-person types.
  location: string | null
  instructions: string | null
  scheduling_window_days: number
  sort_order: number
  // Which User's connected Microsoft Calendar the public apply flow checks
  // for availability and books onto (see microsoft_calendar.py) - only meaningful
  // alongside duration_minutes, same as needsDuration() gates in the editor.
  interviewer_user_id: number | null
  interviewer_name: string | null
}

// A user eligible to be assigned as a stage's interviewer - id/name only
// (see GET /api/organization/interviewers, deliberately smaller than User).
export interface Interviewer {
  id: number
  name: string
}

// A stage already defined on some other job, offered up in the "add existing
// meeting stage" picker. Not yet attached to the current job (no id/sort_order).
export interface AvailableMeetingStage {
  meeting_type: StageMeetingType
  stage_name: string
  duration_minutes: number | null
  default_capacity: number | null
  location: string | null
  instructions: string | null
}

export interface Job {
  id: number
  title: string
  status: JobStatus
  job_type: JobType[]
  city: string | null
  state: string | null
  postal_code: string | null
  country: string | null
  location: string | null
  min_salary: number | null
  max_salary: number | null
  salary_period: SalaryPeriod | null
  highlights: string[]
  description: string | null
  created_at: string
  candidate_count: number
  meeting_stages: MeetingStageTemplate[]
}

export type StageProgressStatus = 'Upcoming' | 'Completed' | 'Cancelled' | 'No show'

// A stage-progress summary for whichever meeting stage is "current" for the
// candidate, surfaced on the list view — the soonest upcoming one, else the
// most recently touched one.
export interface CurrentStageSummary {
  meeting_stage_template_id: number
  stage_name: string | null
  status: StageProgressStatus
  scheduled_at: string | null
}

export interface Candidate {
  id: number
  name: string
  email: string
  phone: string | null
  job_id: number | null
  job_title: string | null
  stage: Stage
  status: string
  interviewer: string | null
  scheduled: boolean
  city: string | null
  state: string | null
  address_line1: string | null
  postal_code: string | null
  location: string | null
  source: string | null
  has_resume: boolean
  resume_filename: string | null
  // Answers to the public apply flow's two fixed work-eligibility questions
  // (routes/apply.py) - null for candidates who didn't come through it.
  // Informational only, never auto-disqualifying.
  work_authorized: boolean | null
  requires_visa_sponsorship: boolean | null
  created_at: string
  updated_at: string
  current_stage: CurrentStageSummary | null
}

export interface ScreeningQuestion {
  id: number
  meeting_stage_template_id: number
  question_text: string
  question_label: string | null
  // A multiple-choice question candidates pick one option from; empty means a
  // free-text question with no fixed options.
  answer_options: string[]
  // Subset of answer_options that qualifies a candidate to proceed.
  qualified_answers: string[]
  sort_order: number
}

export type OnboardingItemType = 'file_upload'

export interface OnboardingDocumentItem {
  id: number
  meeting_stage_template_id: number
  description: string
  type: OnboardingItemType
  required: boolean
  sort_order: number
}

export interface CandidateScreeningAnswer {
  question_id: number
  question_text: string
  answer_options: string[]
  // Subset of answer_options that qualifies the candidate - empty for a
  // free-text question (answer_options also empty), which has no defined
  // "wrong" answer. See ScreeningAnswers.tsx for how this decides the
  // check/✕ shown next to each answer.
  qualified_answers: string[]
  answer_text: string | null
}

// A candidate's progress through one of their job's meeting stages — merges the
// stage template with whatever scheduling/scorecard progress exists so far
// (id is null until the recruiter first touches this stage for this candidate).
export interface CandidateStage {
  meeting_stage_template_id: number
  stage_name: string
  meeting_type: StageMeetingType
  id: number | null
  status: StageProgressStatus
  scheduled_at: string | null
  location: string | null
  notes: string | null
  score_communication: number | null
  score_energy: number | null
  score_relevant_experience: number | null
  // Set together when a recruiter cancels via the "Cancel interview" modal.
  // Recorded only - neither triggers any actual notification (see
  // CandidateStageProgress in models.py).
  cancellation_reason: string | null
  prompt_reschedule: boolean | null
}

export interface CandidateDocumentSubmission {
  id: number
  onboarding_item_id: number
  original_filename: string
  uploaded_at: string
}

export interface CandidateDocumentChecklistItem {
  item_id: number
  description: string
  type: OnboardingItemType
  required: boolean
  submission: CandidateDocumentSubmission | null
}

export interface CandidateDetail extends Candidate {
  screening_answers: CandidateScreeningAnswer[]
  stages: CandidateStage[]
  documents: Partial<Record<number, CandidateDocumentSubmission>>
}

export interface InterviewCandidate {
  id: number
  name: string
}

export interface Interview {
  id: number
  job_id: number | null
  job_title: string | null
  // The real link back to the stage this session belongs to — null for
  // sessions created before this FK existed, or ad-hoc ones with no stage
  // template. stage_name is a denormalized display copy kept in sync via
  // this id, not the other way around.
  meeting_stage_template_id: number | null
  stage_name: string
  meeting_type: MeetingType
  location: string | null
  scheduled_start: string
  scheduled_end: string
  capacity: number
  scheduled_count: number
  candidates: InterviewCandidate[]
  created_at: string
}

// --- Public apply flow (no login — see backend/routes/apply.py, status.py) ---

// Deliberately smaller than Job — a hand-picked public contract, not the
// recruiter-side shape (see routes/apply.py's get_public_job docstring).
export interface PublicJob {
  id: number
  title: string
  location: string | null
  description: string | null
  highlights: string[]
  job_type: JobType[]
  min_salary: number | null
  max_salary: number | null
  salary_period: SalaryPeriod | null
  // For the apply form's EEO notice - the real Organization name (see
  // models.Organization), not hardcoded, so it's never wrong/stale if the
  // org's name ever changes or this is reused by a different deployment.
  organization_name: string
  // Answered as part of applying (see PublicApplyPage) - qualification is
  // evaluated automatically right after submission (see routes/apply.py's
  // apply()), so unlike the recruiter-facing Pre-screen tab, a candidate
  // never sees the outcome directly, only which email (if any) they get.
  screening_questions: PublicScreeningQuestion[]
}

export interface PublicScreeningQuestion {
  id: number
  question_text: string
  answer_options: string[]
}

// --- Public careers landing page (GET /, see routes/public.py) -------------

export interface PublicOrganizationInfo {
  name: string
  has_logo: boolean
}

// A job card on the landing page's job list - deliberately smaller than
// PublicJob (no description/highlights/screening_questions - those only
// matter once a specific job's apply page is open).
export interface PublicJobSummary {
  id: number
  title: string
  location: string | null
  job_type: JobType[]
  min_salary: number | null
  max_salary: number | null
  salary_period: SalaryPeriod | null
  // Included here (unlike a typical list endpoint) so the landing page's
  // per-job "Show Details" accordion can expand in place with no second
  // request - see routes/public.py's list_public_jobs.
  description: string | null
}

export interface PublicSlot {
  start: string
  end: string
}

export interface PublicApplicationOpen {
  already_scheduled: false
  job_title: string
  organization_name: string
  stage_name: string | null
  meeting_type: StageMeetingType | null
  duration_minutes: number | null
  available_slots: PublicSlot[]
}

// The shape GET /api/apply/<token> returns once a candidate has already
// booked through this same flow — no questions/slots, just what they booked.
export interface PublicApplicationScheduled {
  already_scheduled: true
  job_title: string
  organization_name: string
  stage_name: string | null
  scheduled_start: string | null
  scheduled_end: string | null
  meeting_link: string | null
  confirmation_code: string | null
}

export type PublicApplication = PublicApplicationOpen | PublicApplicationScheduled

export interface BookingConfirmation {
  confirmation_code: string
  meeting_link: string | null
  scheduled_start: string
  scheduled_end: string
  status_url: string
}

export interface ApplicationStatus {
  candidate_name: string | null
  job_title: string | null
  stage_name: string
  scheduled_start: string
  scheduled_end: string
  meeting_link: string | null
  confirmation_code: string
  // Same shape/source as the recruiter-side checklist (Job.onboarding_items,
  // aggregated across the job's stages) - this is how a candidate submits
  // onboarding documents themselves, since they have no login of their own
  // (see routes/status.py's POST /api/status/documents).
  onboarding_documents: CandidateDocumentChecklistItem[]
}

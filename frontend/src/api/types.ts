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

export interface User {
  id: number
  first_name: string
  last_name: string
  name: string
  phone: string | null
  email: string
  role: string
  created_at: string
}

// A prospective candidate's own login — separate identity from Candidate,
// which is the per-job application/pipeline record recruiters manage.
export interface CandidateAccount {
  id: number
  first_name: string
  last_name: string
  name: string
  phone: string | null
  email: string
  is_active: boolean
  created_at: string
}

export interface MeetingStageTemplate {
  id: number
  job_id: number
  meeting_type: StageMeetingType
  stage_name: string
  duration_minutes: number | null
  scheduling_window_days: number
  sort_order: number
}

// A stage already defined on some other job, offered up in the "add existing
// meeting stage" picker. Not yet attached to the current job (no id/sort_order).
export interface AvailableMeetingStage {
  meeting_type: StageMeetingType
  stage_name: string
  duration_minutes: number | null
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
  location: string | null
  source: string | null
  has_resume: boolean
  resume_filename: string | null
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

export interface CandidateScreeningAnswer {
  question_id: number
  question_text: string
  answer_options: string[]
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
}

export type CandidateDocumentType = 'drivers_license' | 'nursing_license' | 'ssn_card' | 'xray_ppd'

export interface CandidateDocumentSubmission {
  id: number
  doc_type: CandidateDocumentType
  original_filename: string
  uploaded_at: string
}

export interface CandidateDocumentChecklistItem {
  doc_type: CandidateDocumentType
  label: string
  submission: CandidateDocumentSubmission | null
}

export interface CandidateDetail extends Candidate {
  screening_answers: CandidateScreeningAnswer[]
  stages: CandidateStage[]
  documents: Partial<Record<CandidateDocumentType, CandidateDocumentSubmission>>
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

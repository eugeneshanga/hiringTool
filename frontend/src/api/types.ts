export type Stage = 'Applied' | 'Interview' | 'Offer' | 'Hired' | 'Rejected'
export type JobStatus = 'Published' | 'Draft' | 'Closed'
export type JobType = 'Full-time' | 'Part-time' | 'Remote'
export type SalaryPeriod = 'Hourly' | 'Salary'
export type MeetingType = 'Interview' | 'Orientation' | 'Other'

export interface User {
  id: number
  name: string
  email: string
  role: string
  created_at: string
}

export interface MeetingStageTemplate {
  id: number
  job_id: number
  meeting_type: MeetingType
  stage_name: string
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

export interface Candidate {
  id: number
  name: string
  email: string
  phone: string | null
  job_id: number | null
  stage: Stage
  status: string
  interviewer: string | null
  scheduled: boolean
  created_at: string
}

export interface InterviewCandidate {
  id: number
  name: string
}

export interface Interview {
  id: number
  job_id: number | null
  job_title: string | null
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

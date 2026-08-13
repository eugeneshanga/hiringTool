export type Stage = 'Applied' | 'Interview' | 'Offer' | 'Hired' | 'Rejected'
export type JobStatus = 'Open' | 'Closed' | 'Draft'

export interface User {
  id: number
  name: string
  email: string
  role: string
  created_at: string
}

export interface Job {
  id: number
  title: string
  department: string | null
  location: string | null
  status: JobStatus
  description: string | null
  created_at: string
  candidate_count: number
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
  meeting_type: string
  location: string | null
  scheduled_start: string
  scheduled_end: string
  capacity: number
  scheduled_count: number
  candidates: InterviewCandidate[]
  created_at: string
}

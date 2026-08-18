import type { MeetingType, StageMeetingType } from '../api/types'

export const MEETING_TYPES: { type: StageMeetingType; hint: string }[] = [
  { type: 'Virtual interview', hint: 'A video call interview conducted remotely.' },
  { type: 'In-person interview', hint: 'An interview conducted at a physical location.' },
  { type: 'In-person orientation', hint: 'An in-person session to onboard a new hire.' },
  { type: 'Instant meeting link', hint: 'A reusable meeting link candidates can join anytime.' },
]

export const DEFAULT_DURATION = '10'

export function needsDuration(type: StageMeetingType | '') {
  return type === 'Virtual interview' || type === 'In-person interview'
}

// Interview.meeting_type still uses the older, narrower vocabulary than
// MeetingStageTemplate.meeting_type — map into it when scheduling a session
// for a stage, since there's no exact one-to-one equivalent.
export function toInterviewMeetingType(type: StageMeetingType): MeetingType {
  switch (type) {
    case 'In-person orientation':
      return 'Orientation'
    case 'Instant meeting link':
      return 'Other'
    default:
      return 'Interview'
  }
}

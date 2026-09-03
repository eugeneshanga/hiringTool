// Shared by ScheduleInterviewModal.tsx (recruiter-side "Schedule interview")
// and publicApply/ScheduleApplicationPage.tsx (candidate-side booking) -
// both render the same month-grid-plus-day-panel calendar, just against
// different data (existing sessions vs. live Microsoft Calendar availability).

export function pad(n: number) {
  return String(n).padStart(2, '0')
}

export function dateKey(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function startOfMonth(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

/** 42 cells (6 full weeks) covering the given month, starting on the Sunday
 * on or before the 1st — enough to render a standard month grid. */
export function buildCalendarCells(month: Date) {
  const first = startOfMonth(month)
  const start = new Date(first)
  start.setDate(start.getDate() - first.getDay())
  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(start)
    date.setDate(start.getDate() + i)
    return date
  })
}

export function isSameDay(a: Date, b: Date) {
  return dateKey(a) === dateKey(b)
}

import { useState } from 'react'
import { api, ApiError } from '../../api/client'
import { useSavedFlash } from '../../hooks/useSavedFlash'
import type { CandidateDetail } from '../../api/types'

interface ScreeningAnswersProps {
  candidate: CandidateDetail
  onCandidateChange: (candidate: CandidateDetail) => void
  onError: (message: string) => void
}

function buildAnswerMap(candidate: CandidateDetail) {
  const map: Record<number, string> = {}
  candidate.screening_answers.forEach((a) => {
    map[a.question_id] = a.answer_text ?? ''
  })
  return map
}

/** The job's pre-screening question bank with this candidate's editable
 * answers — green check marks fill in as each one gets a non-empty answer. */
export function ScreeningAnswers({ candidate, onCandidateChange, onError }: ScreeningAnswersProps) {
  const [answers, setAnswers] = useState<Record<number, string>>(() => buildAnswerMap(candidate))
  const [savingAnswers, setSavingAnswers] = useState(false)
  const answersSaved = useSavedFlash()

  function handleAnswerChange(questionId: number, text: string) {
    setAnswers((prev) => ({ ...prev, [questionId]: text }))
  }

  async function handleSaveAnswers() {
    setSavingAnswers(true)
    try {
      const payload = Object.entries(answers).map(([questionId, answerText]) => ({
        question_id: Number(questionId),
        answer_text: answerText,
      }))
      onCandidateChange(await api.updateScreeningAnswers(candidate.id, payload))
      answersSaved.flash()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to save answers')
    } finally {
      setSavingAnswers(false)
    }
  }

  if (candidate.screening_answers.length === 0) return null

  return (
    <div className="card section">
      <div className="section-header">
        <h2>Pre-screening questions</h2>
        <div className="save-control">
          <button type="button" onClick={handleSaveAnswers} disabled={savingAnswers}>
            {savingAnswers ? 'Saving…' : 'Save'}
          </button>
          {answersSaved.saved && <span className="save-confirmation">✓ Saved</span>}
        </div>
      </div>
      <div className="screening-list">
        {candidate.screening_answers.map((a) => {
          const value = answers[a.question_id] ?? ''
          return (
            <div key={a.question_id} className="screening-row">
              <span className={`screening-check${value.trim() ? ' answered' : ''}`}>✓</span>
              <div className="screening-row-body">
                <strong>{a.question_text}</strong>
                <input value={value} onChange={(e) => handleAnswerChange(a.question_id, e.target.value)} />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

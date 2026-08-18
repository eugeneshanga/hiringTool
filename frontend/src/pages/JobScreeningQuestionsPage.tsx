import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import type { JobScreeningQuestion } from '../api/types'
import { useJobDetailContext } from './JobDetailLayout'

export function JobScreeningQuestionsPage() {
  const { job } = useJobDetailContext()
  const [questions, setQuestions] = useState<JobScreeningQuestion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [questionText, setQuestionText] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setQuestions(await api.listScreeningQuestions(job.id))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load screening questions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id])

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (!questionText.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      await api.createScreeningQuestion(job.id, questionText.trim())
      setQuestionText('')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to add question')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(question: JobScreeningQuestion) {
    setError(null)
    try {
      await api.deleteScreeningQuestion(job.id, question.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove question')
    }
  }

  return (
    <div>
      {error && <div className="error-banner">{error}</div>}

      <div className="card section">
        <div className="section-header">
          <h2>Pre-screening questions</h2>
        </div>
        <p className="subtle">
          Candidates for this job answer these on their profile — asked once here, shown and
          editable per candidate on their details page.
        </p>

        {loading ? (
          <p className="subtle">Loading…</p>
        ) : questions.length === 0 ? (
          <p className="subtle">No screening questions yet.</p>
        ) : (
          <ul className="question-list">
            {questions.map((q) => (
              <li key={q.id}>
                <span>{q.question_text}</span>
                <button className="link-button danger" onClick={() => handleRemove(q)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        <form className="form-row enroll-add" onSubmit={handleAdd} style={{ marginTop: '1rem' }}>
          <input
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
            placeholder="e.g. Do you have a current LPN or RN license?"
          />
          <button type="submit" disabled={submitting || !questionText.trim()}>
            {submitting ? 'Adding…' : 'Add question'}
          </button>
        </form>
      </div>
    </div>
  )
}

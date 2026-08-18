import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import type { ScreeningQuestion } from '../api/types'
import { useStageEditorContext } from './StageEditorLayout'

type ModalStep = 'closed' | 'question' | 'qualify'

function parseOptions(text: string) {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

/** The Stage editor's "Pre-screen" tab: this stage's qualifying questions,
 * numbered, with add/edit/delete. Questions with answer options go through a
 * two-step modal (question details, then which answers qualify) mirroring
 * hellohire's "Registration question" / "Select minimum requirements" flow. */
export function StagePreScreenPage() {
  const { job, template } = useStageEditorContext()
  const [questions, setQuestions] = useState<ScreeningQuestion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  const [modalStep, setModalStep] = useState<ModalStep>('closed')
  const [editingQuestion, setEditingQuestion] = useState<ScreeningQuestion | null>(null)
  const [questionText, setQuestionText] = useState('')
  const [questionLabel, setQuestionLabel] = useState('')
  const [answerOptionsText, setAnswerOptionsText] = useState('')
  const [qualifiedAnswers, setQualifiedAnswers] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  const parsedOptions = parseOptions(answerOptionsText)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setQuestions(await api.listStageScreeningQuestions(job.id, template.id))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load screening questions')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, template.id])

  function openAdd() {
    setEditingQuestion(null)
    setQuestionText('')
    setQuestionLabel('')
    setAnswerOptionsText('')
    setQualifiedAnswers([])
    setModalStep('question')
  }

  function openEdit(question: ScreeningQuestion) {
    setEditingQuestion(question)
    setQuestionText(question.question_text)
    setQuestionLabel(question.question_label ?? '')
    setAnswerOptionsText(question.answer_options.join('\n'))
    setQualifiedAnswers(question.qualified_answers)
    setModalStep('question')
  }

  function closeModal() {
    setModalStep('closed')
  }

  function goToQualifyStep() {
    if (!questionText.trim()) return
    // Keep only still-valid selections if options changed since last save.
    setQualifiedAnswers((prev) => prev.filter((a) => parsedOptions.includes(a)))
    setModalStep('qualify')
  }

  function toggleQualified(option: string) {
    setQualifiedAnswers((prev) =>
      prev.includes(option) ? prev.filter((a) => a !== option) : [...prev, option],
    )
  }

  async function saveQuestion(overrides?: { answer_options: string[]; qualified_answers: string[] }) {
    if (!questionText.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const data = {
        question_text: questionText.trim(),
        question_label: questionLabel.trim() || null,
        answer_options: overrides?.answer_options ?? parsedOptions,
        qualified_answers: overrides?.qualified_answers ?? [],
      }
      if (editingQuestion) {
        await api.updateStageScreeningQuestion(job.id, template.id, editingQuestion.id, data)
      } else {
        await api.createStageScreeningQuestion(job.id, template.id, data)
      }
      closeModal()
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save question')
    } finally {
      setSubmitting(false)
    }
  }

  function handleQuestionStepSubmit() {
    if (parsedOptions.length > 0) {
      goToQualifyStep()
    } else {
      saveQuestion({ answer_options: [], qualified_answers: [] })
    }
  }

  function handleQualifyStepSave() {
    saveQuestion({ answer_options: parsedOptions, qualified_answers: qualifiedAnswers })
  }

  function toggleAnswersExpanded(questionId: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(questionId)) next.delete(questionId)
      else next.add(questionId)
      return next
    })
  }

  async function handleRemove(question: ScreeningQuestion) {
    setError(null)
    try {
      await api.deleteStageScreeningQuestion(job.id, template.id, question.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove question')
    }
  }

  return (
    <div className="card section">
      <div className="section-header">
        <h2>Screening and registration questions</h2>
        <button type="button" onClick={openAdd}>
          Add question
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : questions.length === 0 ? (
        <p className="subtle">No screening questions for this stage yet.</p>
      ) : (
        <ol className="stage-list">
          {questions.map((q, index) => {
            const isExpanded = expandedIds.has(q.id)
            return (
              <li key={q.id} className="stage-list-item">
                <div className="stage-row">
                  <span className="stage-number">{index + 1}</span>
                  <div className="stage-info">
                    <div className="stage-name">{q.question_text}</div>
                    <div className="subtle">Mandatory | Pre-screen</div>
                    {q.answer_options.length > 0 && (
                      <button
                        type="button"
                        className="link-button show-answers-toggle"
                        onClick={() => toggleAnswersExpanded(q.id)}
                      >
                        {isExpanded ? 'Hide answers ˄' : 'Show answers ˅'}
                      </button>
                    )}
                  </div>
                  <div className="question-row-actions">
                    <button type="button" className="icon-button" onClick={() => openEdit(q)} aria-label="Edit question">
                      ✎
                    </button>
                    <button
                      type="button"
                      className="icon-button danger"
                      onClick={() => handleRemove(q)}
                      aria-label="Remove question"
                    >
                      🗑
                    </button>
                  </div>
                </div>
                {isExpanded && q.answer_options.length > 0 && (
                  <ul className="answer-preview-list">
                    {q.answer_options.map((option) => {
                      const qualifies = q.qualified_answers.includes(option)
                      return (
                        <li
                          key={option}
                          className={`answer-preview-item${qualifies ? ' qualified' : ' disqualified'}`}
                        >
                          <span aria-hidden="true">{qualifies ? '✓' : '✗'}</span>
                          {option}
                        </li>
                      )
                    })}
                  </ul>
                )}
              </li>
            )
          })}
        </ol>
      )}

      {modalStep === 'question' && (
        <Modal title="Registration question" onClose={closeModal}>
          <div className="form">
            <div className="question-type-box">
              <label>
                Question type
                <select value="Pre-screen" disabled>
                  <option>Pre-screen</option>
                </select>
              </label>
              <p className="subtle">
                Candidates select 1 answer from a list of options to qualify or disqualify them from
                interviewing.
              </p>
            </div>

            <label>
              <span>
                Question{' '}
                <span className="info-icon" title="The question candidates are asked." aria-hidden="true">
                  ⓘ
                </span>
              </span>
              <input value={questionText} onChange={(e) => setQuestionText(e.target.value)} required autoFocus />
            </label>

            <label>
              <span>
                Question label{' '}
                <span
                  className="info-icon"
                  title="A short internal name for this question — not shown to candidates."
                  aria-hidden="true"
                >
                  ⓘ
                </span>
              </span>
              <input value={questionLabel} onChange={(e) => setQuestionLabel(e.target.value)} />
            </label>

            <label>
              Answer options (one option per line)
              <textarea
                rows={4}
                value={answerOptionsText}
                onChange={(e) => setAnswerOptionsText(e.target.value)}
                placeholder={'Yes\nNo'}
              />
            </label>

            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={closeModal}>
                Cancel
              </button>
              <button type="button" onClick={handleQuestionStepSubmit} disabled={submitting || !questionText.trim()}>
                {parsedOptions.length > 0 ? 'Select qualified answers' : submitting ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {modalStep === 'qualify' && (
        <Modal title="Select minimum requirements" onClose={closeModal}>
          <div className="form">
            <p>Select which option(s) allow candidates to register.</p>
            <p className="subtle">Disqualified candidates are notified that they are unable to register at this time.</p>
            <p>
              <strong>Qualification question:</strong> {questionText}
            </p>

            <div className="qualify-options">
              {parsedOptions.map((option) => {
                const selected = qualifiedAnswers.includes(option)
                return (
                  <button
                    key={option}
                    type="button"
                    className={`qualify-option${selected ? ' qualified' : ' disqualified'}`}
                    onClick={() => toggleQualified(option)}
                  >
                    <span className="qualify-checkbox">{selected ? '✓' : ''}</span>
                    {option}
                  </button>
                )
              })}
            </div>

            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setModalStep('question')}>
                Back
              </button>
              <button type="button" onClick={handleQualifyStepSave} disabled={submitting}>
                {submitting ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import { needsOnboarding } from '../lib/meetingStageTypes'
import type { OnboardingDocumentItem } from '../api/types'
import { useStageEditorContext } from './StageEditorLayout'

/** The Stage editor's "Onboarding" tab: this stage's required (or optional)
 * onboarding documents, numbered, with add/edit/delete — mirrors
 * StagePreScreenPage.tsx's editor UI, minus the answer-options/qualify step
 * (an onboarding item has no qualifying answers, just a description and
 * whether it's required). */
export function StageOnboardingPage() {
  const { job, template } = useStageEditorContext()
  const [items, setItems] = useState<OnboardingDocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showModal, setShowModal] = useState(false)
  const [editingItem, setEditingItem] = useState<OnboardingDocumentItem | null>(null)
  const [description, setDescription] = useState('')
  const [required, setRequired] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setItems(await api.listStageOnboardingItems(job.id, template.id))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load onboarding items')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id, template.id])

  function openAdd() {
    setEditingItem(null)
    setDescription('')
    setRequired(true)
    setShowModal(true)
  }

  function openEdit(item: OnboardingDocumentItem) {
    setEditingItem(item)
    setDescription(item.description)
    setRequired(item.required)
    setShowModal(true)
  }

  function closeModal() {
    setShowModal(false)
  }

  async function handleSave() {
    if (!description.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const data = { description: description.trim(), type: 'file_upload' as const, required }
      if (editingItem) {
        await api.updateStageOnboardingItem(job.id, template.id, editingItem.id, data)
      } else {
        await api.createStageOnboardingItem(job.id, template.id, data)
      }
      closeModal()
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save onboarding item')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(item: OnboardingDocumentItem) {
    setError(null)
    try {
      await api.deleteStageOnboardingItem(job.id, template.id, item.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove onboarding item')
    }
  }

  // Onboarding only applies to interview stages (see needsOnboarding) - bounce
  // away if this is reached directly, e.g. a stale link or the stage's type
  // was changed to orientation/instant-link while this tab was open.
  if (!needsOnboarding(template.meeting_type)) {
    return <Navigate to={`/jobs/${job.id}/meeting-stages/${template.id}`} replace />
  }

  return (
    <div className="card section">
      <div className="section-header">
        <h2>Onboarding items</h2>
        <button type="button" onClick={openAdd}>
          Add item
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : items.length === 0 ? (
        <p className="subtle">No onboarding items for this stage yet.</p>
      ) : (
        <ol className="stage-list">
          {items.map((item, index) => (
            <li key={item.id} className="stage-list-item">
              <div className="stage-row">
                <span className="stage-number">{index + 1}</span>
                <div className="stage-info">
                  <div className="stage-name">{item.description}</div>
                  <div className="subtle">
                    {item.required ? 'Required' : 'Optional'} | File upload
                  </div>
                </div>
                <div className="question-row-actions">
                  <button type="button" className="icon-button" onClick={() => openEdit(item)} aria-label="Edit item">
                    ✎
                  </button>
                  <button
                    type="button"
                    className="icon-button danger"
                    onClick={() => handleRemove(item)}
                    aria-label="Remove item"
                  >
                    🗑
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}

      {showModal && (
        <Modal title="Onboarding item" onClose={closeModal}>
          <div className="form">
            <div className="question-type-box">
              <label>
                Type
                <select value="File upload" disabled>
                  <option>File upload</option>
                </select>
              </label>
              <p className="subtle">Candidates upload a file to satisfy this item.</p>
            </div>

            <label>
              <span>
                Description{' '}
                <span className="info-icon" title="What the candidate is asked to provide." aria-hidden="true">
                  ⓘ
                </span>
              </span>
              <input value={description} onChange={(e) => setDescription(e.target.value)} required autoFocus />
            </label>

            <label className="checkbox-label">
              <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} />
              Required
            </label>

            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={closeModal}>
                Cancel
              </button>
              <button type="button" onClick={handleSave} disabled={submitting || !description.trim()}>
                {submitting ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Outlet, useOutletContext, useParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import { ScheduleInterviewModal } from './ScheduleInterviewModal'
import { MEETING_TYPES, needsPreScreen } from '../lib/meetingStageTypes'
import type { Job, MeetingStageTemplate, StageMeetingType } from '../api/types'

export interface StageEditorContext {
  job: Job
  template: MeetingStageTemplate
  reloadTemplate: () => Promise<void>
  onTemplateChange: (template: MeetingStageTemplate) => void
  sessionsVersion: number
  bumpSessionsVersion: () => void
}

export function useStageEditorContext() {
  return useOutletContext<StageEditorContext>()
}

export function StageEditorLayout() {
  const { jobId, templateId } = useParams()
  const [job, setJob] = useState<Job | null>(null)
  const [template, setTemplate] = useState<MeetingStageTemplate | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sessionsVersion, setSessionsVersion] = useState(0)

  const [editingStage, setEditingStage] = useState(false)
  const [editMeetingType, setEditMeetingType] = useState<StageMeetingType>('Virtual interview')
  const [editStageName, setEditStageName] = useState('')
  const [savingStage, setSavingStage] = useState(false)

  const [showScheduleModal, setShowScheduleModal] = useState(false)

  const load = useCallback(async () => {
    if (!jobId || !templateId) return
    try {
      const [jobData, templateData] = await Promise.all([
        api.getJob(Number(jobId)),
        api.getMeetingStage(Number(jobId), Number(templateId)),
      ])
      setJob(jobData)
      setTemplate(templateData)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load meeting stage')
    }
  }, [jobId, templateId])

  useEffect(() => {
    load()
  }, [load])

  function openEditStage() {
    if (!template) return
    setEditMeetingType(template.meeting_type)
    setEditStageName(template.stage_name)
    setEditingStage(true)
  }

  async function handleEditStageSave(e: FormEvent) {
    e.preventDefault()
    if (!job || !template || !editStageName.trim()) return
    setSavingStage(true)
    setError(null)
    try {
      const updated = await api.updateMeetingStage(job.id, template.id, {
        meeting_type: editMeetingType,
        stage_name: editStageName.trim(),
      })
      setTemplate(updated)
      setEditingStage(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save meeting stage')
    } finally {
      setSavingStage(false)
    }
  }

  if (error) {
    return (
      <div className="page">
        <div className="error-banner">{error}</div>
      </div>
    )
  }

  if (!job || !template) {
    return (
      <div className="page">
        <p className="subtle">Loading…</p>
      </div>
    )
  }

  return (
    <div className="job-detail">
      <div className="job-detail-body">
        <aside className="job-detail-sidebar">
          <Link to={`/jobs/${job.id}/meeting-stages`} className="link-button back-link">
            ‹ Back
          </Link>
          <div className="sidebar-group-label">Stage editor</div>
          <div className="sidebar-subgroup-label">Stage</div>
          {needsPreScreen(template.meeting_type) && (
            <NavLink
              to={`/jobs/${job.id}/meeting-stages/${template.id}/pre-screen`}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              Pre-screen
            </NavLink>
          )}
          <NavLink
            to={`/jobs/${job.id}/meeting-stages/${template.id}`}
            end
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            Schedule
          </NavLink>
        </aside>
        <div className="job-detail-content">
          <div className="stage-header-row">
            <div className="job-detail-title-row" style={{ marginBottom: 0 }}>
              <h1>
                {template.stage_name}
                <button type="button" className="icon-button" onClick={openEditStage} aria-label="Edit stage">
                  ✎
                </button>
              </h1>
              <p className="subtle">{template.meeting_type}</p>
            </div>
            <div className="page-header-actions">
              <button type="button" onClick={() => setShowScheduleModal(true)}>
                Schedule interview
              </button>
            </div>
          </div>
          <Outlet
            context={
              {
                job,
                template,
                reloadTemplate: load,
                onTemplateChange: setTemplate,
                sessionsVersion,
                bumpSessionsVersion: () => setSessionsVersion((v) => v + 1),
              } satisfies StageEditorContext
            }
          />
        </div>
      </div>

      {showScheduleModal && (
        <ScheduleInterviewModal
          job={job}
          template={template}
          onClose={() => setShowScheduleModal(false)}
          onScheduled={() => {
            setShowScheduleModal(false)
            setSessionsVersion((v) => v + 1)
          }}
        />
      )}

      {editingStage && (
        <Modal title="Edit meeting stage" onClose={() => setEditingStage(false)}>
          <form onSubmit={handleEditStageSave} className="form">
            <div>
              <label className="modal-field-label">Meeting type:</label>
              <div className="radio-list">
                {MEETING_TYPES.map(({ type, hint }) => (
                  <label key={type} className="radio-option">
                    <input
                      type="radio"
                      name="edit-meeting-type"
                      checked={editMeetingType === type}
                      onChange={() => setEditMeetingType(type)}
                    />
                    {type}
                    <span className="info-icon" title={hint} aria-label={hint}>
                      ⓘ
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <label>
              Meeting name
              <input value={editStageName} onChange={(e) => setEditStageName(e.target.value)} required />
            </label>

            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setEditingStage(false)}>
                Cancel
              </button>
              <button type="submit" disabled={savingStage || !editStageName.trim()}>
                {savingStage ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

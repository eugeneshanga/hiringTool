import { useEffect, useState, type ChangeEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useSavedFlash } from '../hooks/useSavedFlash'
import { usePageTitle } from '../hooks/usePageTitle'
import { useOrganizationContext } from './OrganizationLayout'

interface ImagePickerProps {
  label: string
  hasImage: boolean
  download: () => Promise<{ blob: Blob }>
  upload: (file: File) => Promise<unknown>
  remove: () => Promise<unknown>
  onChange: () => void
}

/** One logo/banner slot: fetches the current image as an authenticated blob
 * (an <img src="/api/..."> can't carry the auth header - same reason
 * document downloads elsewhere in the app go through requestBlob rather
 * than a plain URL) and offers upload/remove. */
function ImagePicker({ label, hasImage, download, upload, remove, onChange }: ImagePickerProps) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let objectUrl: string | null = null
    if (hasImage) {
      download()
        .then(({ blob }) => {
          objectUrl = URL.createObjectURL(blob)
          setPreviewUrl(objectUrl)
        })
        .catch(() => setPreviewUrl(null))
    } else {
      setPreviewUrl(null)
    }
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasImage])

  async function handleUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await upload(file)
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Failed to upload ${label.toLowerCase()}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove() {
    setBusy(true)
    setError(null)
    try {
      await remove()
      onChange()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : `Failed to remove ${label.toLowerCase()}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="image-picker">
      <label className="modal-field-label">
        {label} <span className="info-icon" title={`Shown as the ${label.toLowerCase()}.`} aria-hidden="true">ⓘ</span>
      </label>
      <div className="image-picker-frame">
        {previewUrl ? (
          <img src={previewUrl} alt={label} />
        ) : (
          <span className="subtle">No {label.toLowerCase()} uploaded</span>
        )}
      </div>
      {error && <div className="error-banner">{error}</div>}
      <div className="page-header-actions">
        <label className="link-button">
          {busy ? 'Uploading…' : hasImage ? 'Replace' : 'Upload'}
          <input type="file" accept="image/*" hidden onChange={handleUpload} disabled={busy} />
        </label>
        {hasImage && (
          <button type="button" className="link-button danger" onClick={handleRemove} disabled={busy}>
            Remove
          </button>
        )}
      </div>
    </div>
  )
}

const DAY_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
]

const HOUR_OPTIONS = Array.from({ length: 24 }, (_, hour) => hour)

function formatHourLabel(hour: number) {
  const period = hour < 12 ? 'AM' : 'PM'
  const displayHour = hour % 12 === 0 ? 12 : hour % 12
  return `${displayHour}:00 ${period}`
}

/** The "Organization" tab: editable org name, logo/scheduling-page banner
 * branding, and the working-hours window/days the public apply flow's
 * scheduler offers candidates (see google_calendar.get_free_slots, which
 * reads these same fields). */
export function OrganizationSettingsPage() {
  usePageTitle('Organization - HiringTool')

  const { organization, reloadOrganization } = useOrganizationContext()
  const [name, setName] = useState(organization.name)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameSaved = useSavedFlash()

  const [timezone, setTimezone] = useState(organization.scheduling_timezone)
  const [startHour, setStartHour] = useState(organization.scheduling_working_hours_start)
  const [endHour, setEndHour] = useState(organization.scheduling_working_hours_end)
  const [days, setDays] = useState(organization.scheduling_days)
  const [savingScheduling, setSavingScheduling] = useState(false)
  const [schedulingError, setSchedulingError] = useState<string | null>(null)
  const schedulingSaved = useSavedFlash()

  useEffect(() => {
    setName(organization.name)
  }, [organization.name])

  const schedulingDaysKey = organization.scheduling_days.join(',')

  useEffect(() => {
    setTimezone(organization.scheduling_timezone)
    setStartHour(organization.scheduling_working_hours_start)
    setEndHour(organization.scheduling_working_hours_end)
    setDays(organization.scheduling_days)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    organization.scheduling_timezone,
    organization.scheduling_working_hours_start,
    organization.scheduling_working_hours_end,
    schedulingDaysKey,
  ])

  async function handleSaveName() {
    if (!name.trim() || name === organization.name) return
    setSaving(true)
    setError(null)
    try {
      await api.updateOrganization({ name: name.trim() })
      await reloadOrganization()
      nameSaved.flash()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save organization name')
    } finally {
      setSaving(false)
    }
  }

  function toggleDay(day: number) {
    setDays((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day].sort((a, b) => a - b)))
  }

  async function handleSaveScheduling() {
    if (days.length === 0) {
      setSchedulingError('Select at least one day.')
      return
    }
    setSavingScheduling(true)
    setSchedulingError(null)
    try {
      await api.updateOrganization({
        scheduling_timezone: timezone.trim(),
        scheduling_working_hours_start: startHour,
        scheduling_working_hours_end: endHour,
        scheduling_days: days,
      })
      await reloadOrganization()
      schedulingSaved.flash()
    } catch (err) {
      setSchedulingError(err instanceof ApiError ? err.message : 'Failed to save scheduling settings')
    } finally {
      setSavingScheduling(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Organization</h1>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="card section">
        <label>
          Organization name
          <span className="subtle">Your organization name displays to candidates</span>
          <input value={name} onChange={(e) => setName(e.target.value)} onBlur={handleSaveName} />
        </label>
        {saving && <span className="subtle">Saving…</span>}
        {nameSaved.saved && <span className="save-confirmation">✓ Saved</span>}
      </div>

      <div className="card section">
        <div className="section-header">
          <h2>Branding</h2>
        </div>
        <div className="branding-row">
          <ImagePicker
            label="Logo"
            hasImage={organization.has_logo}
            download={api.downloadOrganizationLogo}
            upload={api.uploadOrganizationLogo}
            remove={api.deleteOrganizationLogo}
            onChange={reloadOrganization}
          />
          <ImagePicker
            label="Scheduling page banner"
            hasImage={organization.has_banner}
            download={api.downloadOrganizationBanner}
            upload={api.uploadOrganizationBanner}
            remove={api.deleteOrganizationBanner}
            onChange={reloadOrganization}
          />
        </div>
      </div>

      <div className="card section">
        <div className="section-header">
          <h2>Scheduling</h2>
        </div>
        <p className="subtle">
          The hours and days candidates can book an interview through the public apply flow.
        </p>

        {schedulingError && <div className="error-banner">{schedulingError}</div>}

        <div className="form-row">
          <label>
            Earliest time
            <select value={startHour} onChange={(e) => setStartHour(Number(e.target.value))}>
              {HOUR_OPTIONS.map((hour) => (
                <option key={hour} value={hour}>
                  {formatHourLabel(hour)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Latest time
            <select value={endHour} onChange={(e) => setEndHour(Number(e.target.value))}>
              {HOUR_OPTIONS.map((hour) => (
                <option key={hour} value={hour}>
                  {formatHourLabel(hour)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Timezone
            <input
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              placeholder="e.g. America/New_York"
            />
          </label>
        </div>

        <label>Available days</label>
        <div className="checkbox-row">
          {DAY_OPTIONS.map((day) => (
            <label key={day.value} className="checkbox-label">
              <input type="checkbox" checked={days.includes(day.value)} onChange={() => toggleDay(day.value)} />
              {day.label}
            </label>
          ))}
        </div>

        <div className="save-control">
          <button type="button" onClick={handleSaveScheduling} disabled={savingScheduling}>
            {savingScheduling ? 'Saving…' : 'Save'}
          </button>
          {schedulingSaved.saved && <span className="save-confirmation">✓ Saved</span>}
        </div>
      </div>
    </div>
  )
}

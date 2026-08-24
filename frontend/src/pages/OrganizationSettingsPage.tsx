import { useEffect, useState, type ChangeEvent } from 'react'
import { api, ApiError } from '../api/client'
import { useSavedFlash } from '../hooks/useSavedFlash'
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

/** The "Organization" tab: editable org name, plus logo/scheduling-page
 * banner branding. */
export function OrganizationSettingsPage() {
  const { organization, reloadOrganization } = useOrganizationContext()
  const [name, setName] = useState(organization.name)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const nameSaved = useSavedFlash()

  useEffect(() => {
    setName(organization.name)
  }, [organization.name])

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
    </div>
  )
}

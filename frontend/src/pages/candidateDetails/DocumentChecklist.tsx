import { useEffect, useState, type ChangeEvent } from 'react'
import { api, ApiError, saveBlob } from '../../api/client'
import type { CandidateDocumentChecklistItem } from '../../api/types'

interface DocumentChecklistProps {
  candidateId: number
  candidateName: string
  onError: (message: string) => void
}

/** The "Onboarding information" card: the candidate's job's onboarding
 * checklist (aggregated across all of the job's stages — see
 * Job.onboarding_items on the backend), per-item upload, and a zip download
 * of everything submitted so far. Renders nothing if the job's stages define
 * no onboarding items at all. */
export function DocumentChecklist({ candidateId, candidateName, onError }: DocumentChecklistProps) {
  const [docChecklist, setDocChecklist] = useState<CandidateDocumentChecklistItem[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [uploadingItemId, setUploadingItemId] = useState<number | null>(null)

  async function loadDocs() {
    setLoadingDocs(true)
    try {
      setDocChecklist(await api.listDocumentChecklist(candidateId))
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to load onboarding documents')
    } finally {
      setLoadingDocs(false)
    }
  }

  useEffect(() => {
    loadDocs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId])

  async function handleDocUpload(itemId: number, e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploadingItemId(itemId)
    try {
      await api.uploadDocument(candidateId, itemId, file)
      await loadDocs()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to upload document')
    } finally {
      setUploadingItemId(null)
    }
  }

  async function handleDownloadDoc(itemId: number, filename: string) {
    try {
      const { blob } = await api.downloadDocument(candidateId, itemId)
      saveBlob(blob, filename)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to download document')
    }
  }

  async function handleDownloadAll() {
    try {
      const { blob } = await api.downloadAllDocuments(candidateId)
      saveBlob(blob, `${candidateName} - documents.zip`)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to download documents')
    }
  }

  // Nothing to show if the candidate's job has no onboarding items defined
  // across any of its stages — don't render an empty card. Wait until
  // loading finishes so this doesn't flash empty before the real list loads.
  if (!loadingDocs && docChecklist.length === 0) {
    return null
  }

  function renderItem(item: CandidateDocumentChecklistItem) {
    return (
      <div key={item.item_id} className="document-row">
        <strong>{item.description}</strong>
        {item.submission ? (
          <p>
            <button
              type="button"
              className="link-button"
              onClick={() => handleDownloadDoc(item.item_id, item.submission!.original_filename)}
            >
              {item.submission.original_filename}
            </button>
          </p>
        ) : (
          <p className="subtle">No submission</p>
        )}
        <label className="link-button">
          {uploadingItemId === item.item_id ? 'Uploading…' : 'Upload ⬆'}
          <input
            type="file"
            hidden
            onChange={(e) => handleDocUpload(item.item_id, e)}
            disabled={uploadingItemId === item.item_id}
          />
        </label>
      </div>
    )
  }

  const requiredItems = docChecklist.filter((item) => item.required)
  const optionalItems = docChecklist.filter((item) => !item.required)

  return (
    <div className="card section">
      <div className="section-header">
        <h2>Onboarding information</h2>
        <button type="button" className="link-button" onClick={handleDownloadAll}>
          Download all ⬇
        </button>
      </div>
      {loadingDocs ? (
        <p className="subtle">Loading…</p>
      ) : (
        <>
          {requiredItems.length > 0 && (
            <>
              <p className="subtle">Required information</p>
              <div className="document-list">{requiredItems.map(renderItem)}</div>
            </>
          )}
          {optionalItems.length > 0 && (
            <>
              <p className="subtle">Optional information</p>
              <div className="document-list">{optionalItems.map(renderItem)}</div>
            </>
          )}
        </>
      )}
    </div>
  )
}

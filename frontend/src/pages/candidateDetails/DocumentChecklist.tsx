import { useEffect, useState, type ChangeEvent } from 'react'
import { api, ApiError, saveBlob } from '../../api/client'
import type { CandidateDocumentChecklistItem, CandidateDocumentType } from '../../api/types'

interface DocumentChecklistProps {
  candidateId: number
  candidateName: string
  onError: (message: string) => void
}

/** The "Onboarding information" card: the fixed required-document checklist,
 * per-item upload, and a zip download of everything submitted so far. */
export function DocumentChecklist({ candidateId, candidateName, onError }: DocumentChecklistProps) {
  const [docChecklist, setDocChecklist] = useState<CandidateDocumentChecklistItem[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [uploadingDocType, setUploadingDocType] = useState<CandidateDocumentType | null>(null)

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

  async function handleDocUpload(docType: CandidateDocumentType, e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploadingDocType(docType)
    try {
      await api.uploadDocument(candidateId, docType, file)
      await loadDocs()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Failed to upload document')
    } finally {
      setUploadingDocType(null)
    }
  }

  async function handleDownloadDoc(docType: CandidateDocumentType, filename: string) {
    try {
      const { blob } = await api.downloadDocument(candidateId, docType)
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

  return (
    <div className="card section">
      <div className="section-header">
        <h2>Onboarding information</h2>
        <button type="button" className="link-button" onClick={handleDownloadAll}>
          Download all ⬇
        </button>
      </div>
      <p className="subtle">Required information</p>
      {loadingDocs ? (
        <p className="subtle">Loading…</p>
      ) : (
        <div className="document-list">
          {docChecklist.map((item) => (
            <div key={item.doc_type} className="document-row">
              <strong>{item.label}</strong>
              {item.submission ? (
                <p>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => handleDownloadDoc(item.doc_type, item.submission!.original_filename)}
                  >
                    {item.submission.original_filename}
                  </button>
                </p>
              ) : (
                <p className="subtle">No submission</p>
              )}
              <label className="link-button">
                {uploadingDocType === item.doc_type ? 'Uploading…' : 'Upload ⬆'}
                <input
                  type="file"
                  hidden
                  onChange={(e) => handleDocUpload(item.doc_type, e)}
                  disabled={uploadingDocType === item.doc_type}
                />
              </label>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

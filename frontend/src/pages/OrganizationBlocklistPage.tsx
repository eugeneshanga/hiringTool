import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import type { BlocklistEntry, BlocklistEntryType } from '../api/types'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** The "Blocklist" tab (admin-only): email addresses/domains barred from
 * becoming a candidate - enforced server-side at candidate self-registration
 * and when a recruiter adds a candidate by hand (see is_email_blocked in
 * models.py). */
export function OrganizationBlocklistPage() {
  const [entries, setEntries] = useState<BlocklistEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showAddModal, setShowAddModal] = useState(false)
  const [type, setType] = useState<BlocklistEntryType>('email')
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setEntries(await api.listBlocklist())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load blocklist')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  function openAddModal() {
    setType('email')
    setValue('')
    setShowAddModal(true)
  }

  async function handleAddSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.createBlocklistEntry({ type, value: value.trim() })
      setShowAddModal(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to add blocklist entry')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(entry: BlocklistEntry) {
    if (!confirm(`Remove ${entry.value} from the blocklist?`)) return
    setError(null)
    try {
      await api.deleteBlocklistEntry(entry.id)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to remove entry')
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Blocklist</h1>
        <button type="button" onClick={openAddModal}>
          Add to blocklist
        </button>
      </div>

      <p className="subtle">
        Emails and domains here are rejected at candidate self-registration and when a recruiter adds a
        candidate by hand.
      </p>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="subtle">Nothing on the blocklist yet.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Value</th>
              <th>Type</th>
              <th>Date added</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.value}</td>
                <td className="subtle">{entry.type}</td>
                <td className="subtle">{formatDate(entry.created_at)}</td>
                <td>
                  <button
                    type="button"
                    className="icon-button danger"
                    onClick={() => handleRemove(entry)}
                    aria-label="Remove from blocklist"
                  >
                    🗑
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showAddModal && (
        <Modal title="Add to blocklist" onClose={() => setShowAddModal(false)}>
          <form onSubmit={handleAddSubmit} className="form">
            <div>
              <label className="modal-field-label">Type:</label>
              <div className="radio-list">
                <label className="radio-option">
                  <input type="radio" checked={type === 'email'} onChange={() => setType('email')} />
                  Email address
                </label>
                <label className="radio-option">
                  <input type="radio" checked={type === 'domain'} onChange={() => setType('domain')} />
                  Domain
                </label>
              </div>
            </div>
            <label>
              {type === 'email' ? 'Email address' : 'Domain'}
              <input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={type === 'email' ? 'someone@example.com' : 'example.com'}
                required
                autoFocus
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button type="submit" disabled={submitting}>
                {submitting ? 'Adding…' : 'Add'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

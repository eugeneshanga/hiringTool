import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api/client'
import { Modal } from '../components/Modal'
import { OverflowMenu } from '../components/OverflowMenu'
import type { User, UserRole } from '../api/types'

const ROLES: UserRole[] = ['admin', 'recruiter', 'interviewer']

/** The "Users & licenses" tab (admin-only): every recruiter/admin/interviewer
 * account, with add/role-change/activate-deactivate/set-password. No
 * license/seat concept exists in this app - "licenses" is just the tab
 * label carried over from the reference design. "Add user"/"Set password"
 * set a credential directly rather than emailing an invite/reset link -
 * there's no email-sending infrastructure here (see StageTabs.tsx's
 * cancel-interview modal for the same constraint) - the admin passes the
 * password to the new user out of band, same as `flask create-user` already
 * requires today. */
export function OrganizationUsersPage() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [showAddModal, setShowAddModal] = useState(false)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [role, setRole] = useState<UserRole>('recruiter')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [passwordTarget, setPasswordTarget] = useState<User | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [settingPassword, setSettingPassword] = useState(false)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setUsers(await api.listOrgUsers())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  function openAddModal() {
    setFirstName('')
    setLastName('')
    setEmail('')
    setPhone('')
    setRole('recruiter')
    setPassword('')
    setShowAddModal(true)
  }

  async function handleAddSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await api.createOrgUser({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone: phone.trim() || null,
        role,
        password,
      })
      setShowAddModal(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to add user')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRoleChange(user: User, newRole: UserRole) {
    setError(null)
    try {
      const updated = await api.updateOrgUser(user.id, { role: newRole })
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to change role')
    }
  }

  async function handleToggleActive(user: User) {
    setError(null)
    try {
      const updated = await api.updateOrgUser(user.id, { is_active: !user.is_active })
      setUsers((prev) => prev.map((u) => (u.id === user.id ? updated : u)))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to update user')
    }
  }

  async function handleSetPassword(e: FormEvent) {
    e.preventDefault()
    if (!passwordTarget) return
    setSettingPassword(true)
    setError(null)
    try {
      await api.setOrgUserPassword(passwordTarget.id, newPassword)
      setPasswordTarget(null)
      setNewPassword('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to set password')
    } finally {
      setSettingPassword(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Users &amp; licenses</h1>
        <button type="button" onClick={openAddModal}>
          Add user
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="subtle">Loading…</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.name}</td>
                <td>{user.email}</td>
                <td>
                  <select value={user.role} onChange={(e) => handleRoleChange(user, e.target.value as UserRole)}>
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <span className={`status-badge ${user.is_active ? 'status-completed' : 'status-cancelled'}`}>
                    {user.is_active ? 'Active' : 'Deactivated'}
                  </span>
                </td>
                <td>
                  <OverflowMenu
                    items={[
                      {
                        label: user.is_active ? 'Deactivate' : 'Reactivate',
                        onClick: () => handleToggleActive(user),
                        danger: user.is_active,
                      },
                      {
                        label: 'Set password',
                        onClick: () => {
                          setPasswordTarget(user)
                          setNewPassword('')
                        },
                      },
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showAddModal && (
        <Modal title="Add user" onClose={() => setShowAddModal(false)}>
          <form onSubmit={handleAddSubmit} className="form">
            <div className="form-row">
              <label>
                First name
                <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required autoFocus />
              </label>
              <label>
                Last name
                <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
              </label>
            </div>
            <label>
              Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </label>
            <label>
              Phone number
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Optional" />
            </label>
            <label>
              Role
              <select value={role} onChange={(e) => setRole(e.target.value as UserRole)}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>
                Password{' '}
                <span
                  className="info-icon"
                  title="Set an initial password and share it with the new user directly - there's no invite email."
                  aria-hidden="true"
                >
                  ⓘ
                </span>
              </span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={8}
                required
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button type="submit" disabled={submitting}>
                {submitting ? 'Adding…' : 'Add user'}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {passwordTarget && (
        <Modal title={`Set password for ${passwordTarget.name}`} onClose={() => setPasswordTarget(null)}>
          <form onSubmit={handleSetPassword} className="form">
            <label>
              New password
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={8}
                required
                autoFocus
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="button-secondary" onClick={() => setPasswordTarget(null)}>
                Cancel
              </button>
              <button type="submit" disabled={settingPassword}>
                {settingPassword ? 'Saving…' : 'Set password'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

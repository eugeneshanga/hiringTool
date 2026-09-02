import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import type { MicrosoftCalendarStatus } from '../api/types'

const CALENDAR_ERROR_MESSAGES: Record<string, string> = {
  access_denied: 'Microsoft sign-in was cancelled.',
  state_expired: 'That connection attempt took too long - try again.',
  invalid_state: 'That connection attempt could not be verified - try again.',
  token_exchange_failed: 'Microsoft rejected the connection attempt - try again.',
  no_refresh_token: 'Microsoft did not grant lasting access - try disconnecting and reconnecting.',
}

/** "Profile" (linked from the header's account dropdown): editable personal
 * info, plus the Microsoft Calendar connection needed for interview/orientation
 * availability. "Done" saves the personal-info form and returns home. */
export function ProfilePage() {
  usePageTitle('Profile - HiringTool')

  const { user, updateUser } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [firstName, setFirstName] = useState(user?.first_name ?? '')
  const [lastName, setLastName] = useState(user?.last_name ?? '')
  const [phone, setPhone] = useState(user?.phone ?? '')
  const [personalMeetingLink, setPersonalMeetingLink] = useState(user?.personal_meeting_link ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [calendarStatus, setCalendarStatus] = useState<MicrosoftCalendarStatus | null>(null)
  const [loadingCalendar, setLoadingCalendar] = useState(true)
  const [disconnecting, setDisconnecting] = useState(false)

  async function loadCalendarStatus() {
    setLoadingCalendar(true)
    try {
      setCalendarStatus(await api.getMicrosoftCalendarStatus())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load calendar status')
    } finally {
      setLoadingCalendar(false)
    }
  }

  useEffect(() => {
    loadCalendarStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The OAuth round-trip (see calendar_auth.py's microsoft_callback) lands back
  // here as a full-page redirect with a query param instead of a response
  // this page's own JS can read directly.
  useEffect(() => {
    if (searchParams.has('calendar_connected')) {
      loadCalendarStatus()
      setSearchParams({}, { replace: true })
    } else if (searchParams.has('calendar_error')) {
      const reason = searchParams.get('calendar_error') ?? ''
      setError(CALENDAR_ERROR_MESSAGES[reason] ?? 'Failed to connect calendar - try again.')
      setSearchParams({}, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  function handleConnectCalendar() {
    window.location.href = api.microsoftCalendarConnectUrl()
  }

  async function handleDisconnectCalendar() {
    if (!confirm('Disconnect your Microsoft Calendar?')) return
    setDisconnecting(true)
    setError(null)
    try {
      await api.disconnectMicrosoftCalendar()
      await loadCalendarStatus()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to disconnect calendar')
    } finally {
      setDisconnecting(false)
    }
  }

  async function handleDone(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const updated = await api.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone: phone.trim() || null,
        personal_meeting_link: personalMeetingLink.trim() || null,
      })
      updateUser(updated)
      navigate('/dashboard')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to save profile')
      setSaving(false)
    }
  }

  if (!user) return null

  return (
    <div className="page profile-page">
      <form onSubmit={handleDone}>
        <div className="page-header">
          <h1>Profile</h1>
          <button type="submit" className="link-button" disabled={saving}>
            {saving ? 'Saving…' : 'Done'}
          </button>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <div className="card section">
          <div className="section-header">
            <h2>Personal info</h2>
          </div>
          <label>
            Email
            <input value={user.email} disabled />
          </label>
          <div className="form-row">
            <label>
              First name
              <input value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
            </label>
            <label>
              Last name
              <input value={lastName} onChange={(e) => setLastName(e.target.value)} required />
            </label>
          </div>
          <label>
            Phone number
            <input value={phone} onChange={(e) => setPhone(e.target.value)} />
          </label>
          <label>
            Meeting link
            <input
              type="url"
              placeholder="https://v.ringcentral.com/join/..."
              value={personalMeetingLink}
              onChange={(e) => setPersonalMeetingLink(e.target.value)}
            />
          </label>
          <p className="subtle">
            Your personal RingCentral meeting link - used for any interview you're assigned to conduct.
            Candidates see this link in their booking confirmation email and status page.
          </p>
        </div>
      </form>

      <div className="card section">
        <div className="section-header">
          <h2>Calendar connection</h2>
        </div>
        <p className="subtle">Connect your calendar in advance to enable faster job setup.</p>

        {loadingCalendar ? (
          <p className="subtle">Loading…</p>
        ) : (
          <>
            {calendarStatus?.connected && (
              <p className="calendar-status-connected">
                <span aria-hidden="true">✓</span> Connected
                {calendarStatus.account_email ? ` (${calendarStatus.account_email})` : ''}
              </p>
            )}
            <div className="page-header-actions">
              {calendarStatus?.connected ? (
                <>
                  <button type="button" className="button-secondary" onClick={handleConnectCalendar}>
                    Reauthorize calendar
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={handleDisconnectCalendar}
                    disabled={disconnecting}
                  >
                    {disconnecting ? 'Disconnecting…' : 'Disconnect'}
                  </button>
                </>
              ) : (
                <button type="button" onClick={handleConnectCalendar}>
                  Connect calendar
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

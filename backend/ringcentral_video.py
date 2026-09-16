"""RingCentral OAuth + token-refresh plumbing, plus per-interview meeting
creation and recording retrieval, via RingCentral's Video API (a private,
3-legged-OAuth app registered in the RingCentral Developer Console - the
"Video" application scope, per that app's setup).

Mirrors microsoft_calendar.py's shape closely (connect/refresh, then a
booking-side action), but is a separate, independent integration - see
models.RingCentralConnection's docstring for why it isn't folded into
CalendarConnection.

What this replaces: previously, every interview conducted over RingCentral
used the interviewer's own static personal_meeting_link (User.
personal_meeting_link) - the same room, reused for every interview they
ever did. That made it impossible to tell which candidate a given
recording belonged to after the fact. create_meeting() below creates a
real, unique RingCentral Video meeting per interview instead (falling back
to the static link if the interviewer hasn't connected RingCentral - see
routes/apply.py's submit_application and routes/candidates.py's
book_stage_slot), and get_meeting_recording_url()/download_recording()
retrieve that specific meeting's recording afterward by its own id
(Interview.ringcentral_meeting_id) - see
scheduled_jobs.fetch_due_interview_recordings.

Caveats worth knowing before touching this file:
- RingCentral's own docs mark the Video REST API as beta - no backwards-
  compatibility guarantee, and this has not been exercised against a real
  RingCentral account/meeting yet (no sandbox access in this environment).
  The HTTP shapes below are built from RingCentral's published
  documentation, not a live-verified integration - the first real
  connect/create/recording-fetch cycle against a real account is the true
  test of this file, and may need small field-name adjustments.
- RingCentral's refresh tokens are short-lived (~7 days) and rotate on
  every use, unlike Microsoft's - an interviewer who goes quiet for over a
  week can end up needing to reconnect from their Profile page.
"""
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet
from flask import current_app

from models import RingCentralConnection, db

RC_API_BASE = 'https://platform.ringcentral.com'
RC_AUTHORIZE_URL = f'{RC_API_BASE}/restapi/oauth/authorize'
RC_TOKEN_URL = f'{RC_API_BASE}/restapi/oauth/token'
RC_EXTENSION_URL = f'{RC_API_BASE}/restapi/v1.0/account/~/extension/~'
RC_BRIDGES_URL = f'{RC_API_BASE}/rcvideo/v2/account/~/extension/~/bridges'
RC_MEETING_HISTORY_URL = f'{RC_API_BASE}/rcvideo/v1/history/meetings'

# "Video" alone is enough for creating meetings and reading meeting
# history/recordings - see this app's own Developer Console app setup.
RINGCENTRAL_SCOPES = 'Video'

REQUEST_TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 30

# Same reasoning as microsoft_calendar.py's identical constant.
EXPIRY_SAFETY_MARGIN_SECONDS = 60


class RingCentralNotConnectedError(Exception):
    """Raised by get_valid_access_token() when the User has no
    RingCentralConnection at all (never connected, or disconnected)."""


class RingCentralTokenError(Exception):
    """Raised when talking to RingCentral's token endpoint fails - a bad/
    expired refresh token (the ~7-day lifetime, or revoked access) is the
    most likely cause once a connection has been working."""


def _fernet():
    # Same key as microsoft_calendar.py's _fernet() - one encryption key for
    # every provider's refresh tokens, not one per provider.
    key = current_app.config.get('CALENDAR_ENCRYPTION_KEY')
    if not key:
        raise RuntimeError('CALENDAR_ENCRYPTION_KEY is not set - see database.env')
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(raw_token):
    return _fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token):
    return _fernet().decrypt(encrypted_token.encode()).decode()


def _basic_auth():
    """RingCentral's token endpoint authenticates the app itself via HTTP
    Basic auth (client_id:client_secret) rather than a client_secret form
    field, unlike Microsoft's token endpoint."""
    return (current_app.config['RINGCENTRAL_CLIENT_ID'], current_app.config['RINGCENTRAL_CLIENT_SECRET'])


def build_authorization_url(state):
    """The URL to send the recruiter's browser to for RingCentral's consent
    screen. `state` should be a signed, short-lived token (see
    routes/ringcentral_auth.py) identifying which User this connection is
    for - RingCentral echoes it back verbatim to the callback."""
    params = {
        'client_id': current_app.config['RINGCENTRAL_CLIENT_ID'],
        'redirect_uri': current_app.config['RINGCENTRAL_REDIRECT_URI'],
        'response_type': 'code',
        'state': state,
    }
    return f'{RC_AUTHORIZE_URL}?{urlencode(params)}'


def exchange_code_for_tokens(code):
    """POSTs the authorization code from the callback to RingCentral's token
    endpoint. Returns the raw JSON dict (access_token, refresh_token,
    expires_in, ...). Raises requests.HTTPError on a non-2xx response."""
    resp = requests.post(
        RC_TOKEN_URL,
        auth=_basic_auth(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': current_app.config['RINGCENTRAL_REDIRECT_URI'],
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_ringcentral_email(access_token):
    """Which RingCentral account was just connected, for display
    (RingCentralConnection.account_email) - not necessarily the same
    address as the recruiter's hiringTool login."""
    resp = requests.get(
        RC_EXTENSION_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get('contact') or {}).get('email') or data.get('name') or 'RingCentral account'


def _refresh_access_token(refresh_token):
    resp = requests.post(
        RC_TOKEN_URL,
        auth=_basic_auth(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={'grant_type': 'refresh_token', 'refresh_token': refresh_token},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not resp.ok:
        raise RingCentralTokenError(f'RingCentral token refresh failed ({resp.status_code}): {resp.text}')
    return resp.json()


def get_valid_access_token(user):
    """Given a User, returns a valid RingCentral access token for their
    connected account - refreshing it first (and persisting the refresh) if
    the stored one is missing or expired. Mirrors microsoft_calendar.py's
    identical function; the one real difference is RingCentral always
    rotates the refresh token on use (Microsoft only sometimes does), so
    the new one is unconditionally persisted here, not just when present.

    Raises RingCentralNotConnectedError if the user has no connection, and
    RingCentralTokenError if RingCentral rejects the refresh (an expired-
    after-~7-days or revoked refresh token being the most likely cause).
    """
    connection = RingCentralConnection.query.filter_by(user_id=user.id).first()
    if not connection:
        raise RingCentralNotConnectedError(f'user {user.id} has no connected RingCentral account')

    now = datetime.utcnow()
    still_valid = (
        connection.access_token
        and connection.token_expiry
        and connection.token_expiry > now + timedelta(seconds=EXPIRY_SAFETY_MARGIN_SECONDS)
    )
    if still_valid:
        return connection.access_token

    refresh_token = decrypt_token(connection.encrypted_refresh_token)
    token_data = _refresh_access_token(refresh_token)

    connection.access_token = token_data['access_token']
    connection.token_expiry = now + timedelta(seconds=token_data.get('expires_in', 3600))
    new_refresh_token = token_data.get('refresh_token')
    if new_refresh_token:
        connection.encrypted_refresh_token = encrypt_token(new_refresh_token)
    db.session.commit()

    return connection.access_token


# --- meeting creation ---------------------------------------------------------

def _create_bridge_request(access_token, name):
    """POSTs a new meeting bridge. Split out from create_meeting so tests
    can monkeypatch just this - same reasoning as microsoft_calendar.py's
    _create_calendar_event_request. type: 'Scheduled' (not the default
    'Instant') - RingCentral doesn't track meeting times itself ("we defer
    to the user's calendaring system as the source of record for when
    meetings occur", per their own docs), so this just gets a durable room
    with a stable id/join link that won't auto-expire in the 3 days an
    'Instant' bridge would - our own scheduled_start/end (and the Microsoft
    Calendar event, when connected) remain the actual source of truth for
    time, same as before this integration existed."""
    resp = requests.post(
        RC_BRIDGES_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        json={'name': name, 'type': 'Scheduled'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def create_meeting(user, topic):
    """Creates a real per-interview RingCentral Video meeting on `user`'s
    connected account. Returns (meeting_id, join_url) - meeting_id is what
    gets stored on Interview.ringcentral_meeting_id so
    scheduled_jobs.fetch_due_interview_recordings can look its recording up
    afterward; join_url is what candidates/interviewers actually use to
    join, same role the static personal_meeting_link used to play.

    Raises requests.RequestException on failure, and whatever
    get_valid_access_token raises if the user's RingCentral account isn't
    connected - callers should catch both and fall back to the
    interviewer's static personal_meeting_link (see routes/apply.py's
    submit_application), same fail-safe posture as everywhere else calendar/
    video integrations are optional in this app.
    """
    access_token = get_valid_access_token(user)
    bridge = _create_bridge_request(access_token, topic)
    join_url = (bridge.get('discovery') or {}).get('web')
    return bridge['id'], join_url


# --- recording retrieval -------------------------------------------------------

def _get_meeting_request(access_token, meeting_id):
    resp = requests.get(
        f'{RC_MEETING_HISTORY_URL}/{meeting_id}',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_meeting_recording_url(user, meeting_id):
    """The download URL for `meeting_id`'s recording, or None if the
    meeting has no recording yet (still processing, recording wasn't
    turned on, or the meeting hasn't happened yet). Callers - see
    scheduled_jobs.fetch_due_interview_recordings - should treat None as
    "check again later," not an error; only genuine request failures raise.
    """
    access_token = get_valid_access_token(user)
    meeting = _get_meeting_request(access_token, meeting_id)
    if not meeting:
        return None
    recordings = meeting.get('recordings') or []
    return recordings[0]['url'] if recordings else None


def download_recording(user, recording_url):
    """Downloads a recording's raw bytes from RingCentral's media domain -
    protected by the same bearer token as the rest of the API (per
    RingCentral's own docs: "the recommended way to pass authentication
    credentials to a media URL is through an HTTP Authorization header").
    Returns the raw bytes; the caller (scheduled_jobs.py) is responsible for
    saving them the same way a manually-uploaded recording would be."""
    access_token = get_valid_access_token(user)
    resp = requests.get(
        recording_url,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=DOWNLOAD_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.content

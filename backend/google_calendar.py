"""Google OAuth + token-refresh plumbing, plus availability/booking, for
calendar integration.

Phase 1 (connect/disconnect/refresh) hands back a valid access token for a
User via get_valid_access_token() - everything below builds on that:
get_free_slots() (freebusy.query, bounded to a configured working-hours
window - see config.py's SCHEDULING_* values) and create_event() (with a
generated Google Meet link) are what the public apply flow (routes/apply.py)
calls to show a candidate open times and then book one.

The low-level HTTP calls (_freebusy_request, _create_calendar_event_request,
_delete_calendar_event_request) are split out from the business logic around
them (slot generation/filtering) specifically so tests can monkeypatch just
the network edge, the same way test_calendar_auth.py already does for
exchange_code_for_tokens/fetch_google_email.
"""
import secrets
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from cryptography.fernet import Fernet
from flask import current_app

from models import CalendarConnection, Organization, db, iso_utc

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'
GOOGLE_FREEBUSY_URL = 'https://www.googleapis.com/calendar/v3/freeBusy'
GOOGLE_EVENTS_URL = 'https://www.googleapis.com/calendar/v3/calendars/primary/events'

# calendar.events is enough to create/read events without also granting
# read/write on calendar *settings*. calendar.freebusy is a separate,
# narrower scope Google requires specifically for the freeBusy.query
# endpoint (get_free_slots below) - calendar.events alone returns a 403
# ("Request had insufficient authentication scopes") on that call, so both
# are needed together even though "events" sounds like it should cover
# "is this person busy". openid email is just so we can label the
# connection with which Google account it is (CalendarConnection.google_email),
# for display purposes.
#
# NOTE: this is a consent-time scope - a User who connected their calendar
# before calendar.freebusy was added here needs to reconnect (disconnect,
# then connect again) to pick it up; their existing refresh token stays
# scoped to whatever they originally consented to.
CALENDAR_SCOPES = 'openid email https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.freebusy'

REQUEST_TIMEOUT_SECONDS = 10

# How much lead time to leave before an access token's real expiry when
# deciding whether it still counts as "valid" - avoids a request racing the
# token expiring mid-flight.
EXPIRY_SAFETY_MARGIN_SECONDS = 60


class CalendarNotConnectedError(Exception):
    """Raised by get_valid_access_token() when the User has no
    CalendarConnection at all (never connected, or disconnected)."""


class CalendarTokenError(Exception):
    """Raised when talking to Google's token endpoint fails - a bad/expired
    refresh token (e.g. the user revoked access from their Google account
    directly) is the most likely cause once a connection has been working."""


def _fernet():
    key = current_app.config.get('CALENDAR_ENCRYPTION_KEY')
    if not key:
        raise RuntimeError(
            'CALENDAR_ENCRYPTION_KEY is not set - see database.env'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(raw_token):
    return _fernet().encrypt(raw_token.encode()).decode()


def decrypt_token(encrypted_token):
    return _fernet().decrypt(encrypted_token.encode()).decode()


def build_authorization_url(state):
    """The URL to send the recruiter's browser to for Google's consent
    screen. `state` should be a signed, short-lived token (see
    routes/calendar_auth.py) identifying which User this connection is for -
    Google echoes it back verbatim to the callback."""
    params = {
        'client_id': current_app.config['GOOGLE_CLIENT_ID'],
        'redirect_uri': current_app.config['GOOGLE_REDIRECT_URI'],
        'response_type': 'code',
        'scope': CALENDAR_SCOPES,
        'access_type': 'offline',
        # Forces Google to re-show the consent screen (and re-issue a
        # refresh_token) even for a user who already granted access before -
        # without this, reconnecting after a disconnect can silently come
        # back with no refresh_token at all, since Google only issues one on
        # a user's *first* consent by default.
        'prompt': 'consent',
        'state': state,
    }
    return f'{GOOGLE_AUTH_URL}?{urlencode(params)}'


def exchange_code_for_tokens(code):
    """POSTs the authorization code from the callback to Google's token
    endpoint. Returns the raw JSON dict (access_token, refresh_token,
    expires_in, ...). Raises requests.HTTPError on a non-2xx response."""
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            'code': code,
            'client_id': current_app.config['GOOGLE_CLIENT_ID'],
            'client_secret': current_app.config['GOOGLE_CLIENT_SECRET'],
            'redirect_uri': current_app.config['GOOGLE_REDIRECT_URI'],
            'grant_type': 'authorization_code',
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_google_email(access_token):
    """Which Google account was just connected, for display
    (CalendarConnection.google_email) - not necessarily the same address as
    the recruiter's hiringTool login."""
    resp = requests.get(
        GOOGLE_USERINFO_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json().get('email')


def _refresh_access_token(refresh_token):
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            'refresh_token': refresh_token,
            'client_id': current_app.config['GOOGLE_CLIENT_ID'],
            'client_secret': current_app.config['GOOGLE_CLIENT_SECRET'],
            'grant_type': 'refresh_token',
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not resp.ok:
        raise CalendarTokenError(
            f'Google token refresh failed ({resp.status_code}): {resp.text}'
        )
    return resp.json()


def get_valid_access_token(user):
    """Given a User, returns a valid Google access token for their connected
    calendar - refreshing it first (and persisting the refresh) if the
    stored one is missing or expired. This is the one function every later
    phase (availability, booking) should call rather than reading
    CalendarConnection.access_token directly.

    Raises CalendarNotConnectedError if the user has no connection, and
    CalendarTokenError if Google rejects the refresh (e.g. the refresh token
    was revoked on Google's side).
    """
    connection = CalendarConnection.query.filter_by(user_id=user.id).first()
    if not connection:
        raise CalendarNotConnectedError(f'user {user.id} has no connected calendar')

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
    db.session.commit()

    return connection.access_token


# --- availability -----------------------------------------------------------

# How much notice a candidate must give before a slot's start time - keeps
# the public page from offering (or accepting) a slot starting in the next
# few minutes that the interviewer would have no realistic chance to see.
MIN_LEAD_TIME_HOURS = 2


def _freebusy_request(access_token, time_min, time_max):
    """Calls freebusy.query for the connected user's primary calendar over
    [time_min, time_max) (naive-UTC datetimes) and returns their busy blocks
    as a list of (start, end) naive-UTC datetime tuples. Split out from
    get_free_slots so tests can monkeypatch just this - see module
    docstring."""
    resp = requests.post(
        GOOGLE_FREEBUSY_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        json={
            'timeMin': iso_utc(time_min),
            'timeMax': iso_utc(time_max),
            'items': [{'id': 'primary'}],
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    busy = resp.json().get('calendars', {}).get('primary', {}).get('busy', [])
    return [
        (
            datetime.fromisoformat(b['start']).astimezone(timezone.utc).replace(tzinfo=None),
            datetime.fromisoformat(b['end']).astimezone(timezone.utc).replace(tzinfo=None),
        )
        for b in busy
    ]


def _candidate_slot_windows(window_days, duration_minutes, working_hours_start, working_hours_end, allowed_weekdays, tz):
    """Every duration_minutes-sized slot inside [working_hours_start,
    working_hours_end) in timezone `tz`, on any day whose date.weekday()
    (Monday=0 .. Sunday=6) is in `allowed_weekdays`, for today through
    `window_days` days out - before any freebusy/lead-time filtering.
    Returns (start, end) naive-UTC datetime tuples, ascending."""
    slots = []
    today_local = datetime.now(tz).date()
    for day_offset in range(window_days + 1):
        day = today_local + timedelta(days=day_offset)
        if day.weekday() not in allowed_weekdays:
            continue
        day_end_local = datetime.combine(day, time(hour=working_hours_end), tzinfo=tz)
        slot_start_local = datetime.combine(day, time(hour=working_hours_start), tzinfo=tz)
        while slot_start_local + timedelta(minutes=duration_minutes) <= day_end_local:
            slot_end_local = slot_start_local + timedelta(minutes=duration_minutes)
            slots.append((
                slot_start_local.astimezone(timezone.utc).replace(tzinfo=None),
                slot_end_local.astimezone(timezone.utc).replace(tzinfo=None),
            ))
            slot_start_local = slot_end_local
    return slots


def get_free_slots(user, duration_minutes, window_days):
    """Every open duration_minutes-sized slot on `user`'s connected Google
    Calendar over the next `window_days` days, bounded to the org's
    configured working-hours window/timezone/allowed days (Organization's
    scheduling_* columns, editable from Settings - see routes/organization.py)
    and excluding anything within MIN_LEAD_TIME_HOURS of right now. Returns a
    list of (start, end) naive-UTC datetime tuples, ascending.

    Raises CalendarNotConnectedError / CalendarTokenError (from
    get_valid_access_token) or requests.RequestException on a Google API
    failure - callers on a public, candidate-facing page should catch these
    and treat them as "no slots available" rather than a 500; see
    routes/apply.py.
    """
    access_token = get_valid_access_token(user)

    # No auto-create here (unlike routes/organization.py's own
    # _get_organization()) - falls back to the same defaults a fresh
    # Organization row would have, without the side effect of creating one
    # from what's ultimately a read path.
    org = Organization.query.first()
    tz = ZoneInfo(org.scheduling_timezone if org else 'UTC')
    working_hours_start = org.scheduling_working_hours_start if org else 9
    working_hours_end = org.scheduling_working_hours_end if org else 17
    allowed_weekdays = set(org.scheduling_days if org and org.scheduling_days else [0, 1, 2, 3, 4])

    candidate_slots = _candidate_slot_windows(
        window_days, duration_minutes, working_hours_start, working_hours_end, allowed_weekdays, tz,
    )
    if not candidate_slots:
        return []

    busy_blocks = _freebusy_request(access_token, candidate_slots[0][0], candidate_slots[-1][1])
    earliest_allowed = datetime.utcnow() + timedelta(hours=MIN_LEAD_TIME_HOURS)

    def _is_free(slot_start, slot_end):
        if slot_start < earliest_allowed:
            return False
        return not any(slot_start < busy_end and slot_end > busy_start for busy_start, busy_end in busy_blocks)

    return [s for s in candidate_slots if _is_free(*s)]


# --- booking ------------------------------------------------------------------

def _create_calendar_event_request(access_token, body):
    """POSTs a new event to the connected user's primary calendar. Split out
    from create_event so tests can monkeypatch just this - see module
    docstring."""
    resp = requests.post(
        GOOGLE_EVENTS_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        params={'conferenceDataVersion': 1},  # required for conferenceData.createRequest to take effect
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _delete_calendar_event_request(access_token, event_id):
    resp = requests.delete(
        f'{GOOGLE_EVENTS_URL}/{event_id}',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    # 410 Gone means it's already deleted/never existed - fine either way,
    # the caller's goal (no such event remains) is already satisfied.
    if resp.status_code not in (204, 410):
        resp.raise_for_status()


def create_event(user, summary, description, start, end, attendee_email=None):
    """Creates a real Google Calendar event on `user`'s primary calendar,
    with a generated Google Meet link (conferenceData.createRequest).
    start/end are naive-UTC datetimes, per this app's storage convention
    (see models.iso_utc). sendUpdates is deliberately omitted (Google
    defaults to not notifying) - the candidate gets their own confirmation
    email (email_sender.send_confirmation_email) rather than a native
    Google Calendar invite, to avoid sending two different-looking
    notifications for the same booking.

    Returns (google_event_id, meeting_link) - meeting_link is None if Google
    didn't return a video entry point (shouldn't normally happen given the
    createRequest above, but the caller shouldn't crash if it does). Raises
    requests.RequestException on failure, and whatever
    get_valid_access_token raises if the user's calendar isn't connected.
    """
    access_token = get_valid_access_token(user)

    body = {
        'summary': summary,
        'description': description,
        'start': {'dateTime': iso_utc(start), 'timeZone': 'UTC'},
        'end': {'dateTime': iso_utc(end), 'timeZone': 'UTC'},
        'conferenceData': {
            'createRequest': {
                'requestId': secrets.token_hex(16),
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
            },
        },
    }
    if attendee_email:
        body['attendees'] = [{'email': attendee_email}]

    event = _create_calendar_event_request(access_token, body)

    meeting_link = next(
        (
            entry.get('uri')
            for entry in event.get('conferenceData', {}).get('entryPoints', [])
            if entry.get('entryPointType') == 'video'
        ),
        None,
    )
    return event['id'], meeting_link


def delete_event(user, google_event_id):
    """Deletes a previously-created event from `user`'s primary calendar -
    used as a best-effort compensating action if a booking fails to persist
    on our side after the calendar event was already created (see
    routes/apply.py's submit endpoint). Raises the same way create_event
    does; callers already treat this as best-effort and catch broadly."""
    access_token = get_valid_access_token(user)
    _delete_calendar_event_request(access_token, google_event_id)

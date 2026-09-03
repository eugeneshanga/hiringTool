"""Microsoft OAuth + token-refresh plumbing, plus availability/booking, for
calendar integration - via Microsoft Graph and an Entra ID (Azure AD) app
registration (see config.py's MICROSOFT_* settings).

Phase 1 (connect/disconnect/refresh) hands back a valid access token for a
User via get_valid_access_token() - everything below builds on that:
get_free_slots() (calendar/getSchedule, bounded to a configured
working-hours window - see config.py's SCHEDULING_* values) and
create_event() are what the public apply flow (routes/apply.py) calls to
show a candidate open times and then book one - interviews themselves are
conducted over RingCentral via the interviewer's own static meeting link
(User.personal_meeting_link), not a link generated per-event here.

The low-level HTTP calls (_get_schedule_request, _create_calendar_event_request,
_delete_calendar_event_request) are split out from the business logic around
them (slot generation/filtering) specifically so tests can monkeypatch just
the network edge, the same way test_calendar_auth.py already does for
exchange_code_for_tokens/fetch_microsoft_email.
"""
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests
from cryptography.fernet import Fernet
from flask import current_app

from models import CalendarConnection, Organization, db, iso_utc

# {tenant} is config.py's MICROSOFT_TENANT ('common' by default - both
# work/school and personal Microsoft accounts).
MICROSOFT_AUTH_URL = 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize'
MICROSOFT_TOKEN_URL = 'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token'
GRAPH_ME_URL = 'https://graph.microsoft.com/v1.0/me'
GRAPH_GET_SCHEDULE_URL = 'https://graph.microsoft.com/v1.0/me/calendar/getSchedule'
GRAPH_EVENTS_URL = 'https://graph.microsoft.com/v1.0/me/events'

# Calendars.ReadWrite covers both booking (POST /events) and availability
# (POST /calendar/getSchedule) - unlike Google, Microsoft Graph doesn't
# split those into two separate scopes. offline_access is what gets a
# refresh_token back at all (without it, the access token is the only thing
# issued, and it's only good for ~1 hour with no way to renew it without the
# user consenting again). openid email/User.Read are just so we can label
# the connection with which Microsoft account it is
# (CalendarConnection.account_email), for display purposes.
CALENDAR_SCOPES = (
    'openid email offline_access '
    'https://graph.microsoft.com/User.Read '
    'https://graph.microsoft.com/Calendars.ReadWrite'
)

REQUEST_TIMEOUT_SECONDS = 10

# How much lead time to leave before an access token's real expiry when
# deciding whether it still counts as "valid" - avoids a request racing the
# token expiring mid-flight.
EXPIRY_SAFETY_MARGIN_SECONDS = 60


class CalendarNotConnectedError(Exception):
    """Raised by get_valid_access_token() when the User has no
    CalendarConnection at all (never connected, or disconnected)."""


class CalendarTokenError(Exception):
    """Raised when talking to Microsoft's token endpoint fails - a bad/
    expired refresh token (e.g. the user revoked access from their
    Microsoft account directly, or an admin revoked the app's consent) is
    the most likely cause once a connection has been working."""


def _tenant():
    return current_app.config.get('MICROSOFT_TENANT') or 'common'


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
    """The URL to send the recruiter's browser to for Microsoft's consent
    screen. `state` should be a signed, short-lived token (see
    routes/calendar_auth.py) identifying which User this connection is for -
    Microsoft echoes it back verbatim to the callback."""
    params = {
        'client_id': current_app.config['MICROSOFT_CLIENT_ID'],
        'redirect_uri': current_app.config['MICROSOFT_REDIRECT_URI'],
        'response_type': 'code',
        'response_mode': 'query',
        'scope': CALENDAR_SCOPES,
        # Forces Microsoft to re-show the consent screen even for a user who
        # already granted access before - without this, reconnecting after a
        # disconnect can silently come back with no refresh_token at all on
        # some tenant configurations.
        'prompt': 'consent',
        'state': state,
    }
    return f'{MICROSOFT_AUTH_URL.format(tenant=_tenant())}?{urlencode(params)}'


def exchange_code_for_tokens(code):
    """POSTs the authorization code from the callback to Microsoft's token
    endpoint. Returns the raw JSON dict (access_token, refresh_token,
    expires_in, ...). Raises requests.HTTPError on a non-2xx response."""
    resp = requests.post(
        MICROSOFT_TOKEN_URL.format(tenant=_tenant()),
        data={
            'code': code,
            'client_id': current_app.config['MICROSOFT_CLIENT_ID'],
            'client_secret': current_app.config['MICROSOFT_CLIENT_SECRET'],
            'redirect_uri': current_app.config['MICROSOFT_REDIRECT_URI'],
            'grant_type': 'authorization_code',
            'scope': CALENDAR_SCOPES,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_microsoft_email(access_token):
    """Which Microsoft account was just connected, for display
    (CalendarConnection.account_email) - not necessarily the same address as
    the recruiter's hiringTool login. `mail` is null for some account types
    (e.g. certain personal Microsoft accounts), so this falls back to
    userPrincipalName, which is always present."""
    resp = requests.get(
        GRAPH_ME_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get('mail') or data.get('userPrincipalName')


def _refresh_access_token(refresh_token):
    resp = requests.post(
        MICROSOFT_TOKEN_URL.format(tenant=_tenant()),
        data={
            'refresh_token': refresh_token,
            'client_id': current_app.config['MICROSOFT_CLIENT_ID'],
            'client_secret': current_app.config['MICROSOFT_CLIENT_SECRET'],
            'grant_type': 'refresh_token',
            'scope': CALENDAR_SCOPES,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not resp.ok:
        raise CalendarTokenError(
            f'Microsoft token refresh failed ({resp.status_code}): {resp.text}'
        )
    return resp.json()


def get_valid_access_token(user):
    """Given a User, returns a valid Microsoft access token for their
    connected calendar - refreshing it first (and persisting the refresh)
    if the stored one is missing or expired. This is the one function every
    later phase (availability, booking) should call rather than reading
    CalendarConnection.access_token directly.

    Raises CalendarNotConnectedError if the user has no connection, and
    CalendarTokenError if Microsoft rejects the refresh (e.g. the refresh
    token was revoked on Microsoft's side).
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
    # Unlike Google, Microsoft may rotate the refresh token on every use -
    # the old one can stop working once a new one's been issued, so this
    # must be persisted whenever present rather than assumed stable.
    new_refresh_token = token_data.get('refresh_token')
    if new_refresh_token:
        connection.encrypted_refresh_token = encrypt_token(new_refresh_token)
    db.session.commit()

    return connection.access_token


# --- availability -----------------------------------------------------------

# How much notice a candidate must give before a slot's start time - keeps
# the public page from offering (or accepting) a slot starting in the next
# few minutes that the interviewer would have no realistic chance to see.
MIN_LEAD_TIME_HOURS = 2


def _get_schedule_request(access_token, account_email, time_min, time_max):
    """Calls calendar/getSchedule for the connected user's own calendar over
    [time_min, time_max) (naive-UTC datetimes) and returns their busy blocks
    as a list of (start, end) naive-UTC datetime tuples. Split out from
    get_free_slots so tests can monkeypatch just this - see module
    docstring.

    Treats every status other than 'free' (busy, tentative, oof, working
    elsewhere) as blocking - a candidate-facing scheduler should err toward
    under- rather than over-offering a slot."""
    resp = requests.post(
        GRAPH_GET_SCHEDULE_URL,
        headers={'Authorization': f'Bearer {access_token}', 'Prefer': 'outlook.timezone="UTC"'},
        json={
            'schedules': [account_email],
            'startTime': {'dateTime': iso_utc(time_min), 'timeZone': 'UTC'},
            'endTime': {'dateTime': iso_utc(time_max), 'timeZone': 'UTC'},
            'availabilityViewInterval': 30,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    schedules = resp.json().get('value', [])
    items = schedules[0].get('scheduleItems', []) if schedules else []
    return [
        (
            _parse_graph_datetime(item['start']['dateTime']),
            _parse_graph_datetime(item['end']['dateTime']),
        )
        for item in items
        if item.get('status') != 'free'
    ]


def _parse_graph_datetime(value):
    """Graph's dateTime strings (already UTC here, per the Prefer header
    above - no offset/'Z' suffix to strip) commonly carry 7 fractional-
    second digits (e.g. '.0000000'), which datetime.fromisoformat() rejects
    - it accepts at most 6. Truncate rather than assume Graph's precision
    matches Python's."""
    if '.' in value:
        whole, frac = value.split('.', 1)
        value = f'{whole}.{frac[:6]}'
    return datetime.fromisoformat(value)


def _candidate_slot_windows(window_days, duration_minutes, working_hours_start, working_hours_end, allowed_weekdays, tz):
    """Every duration_minutes-sized slot inside [working_hours_start,
    working_hours_end) in timezone `tz`, on any day whose date.weekday()
    (Monday=0 .. Sunday=6) is in `allowed_weekdays`, for today through
    `window_days` days out - before any getSchedule/lead-time filtering.
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
    """Every open duration_minutes-sized slot on `user`'s connected
    Microsoft/Outlook Calendar over the next `window_days` days, bounded to
    the org's configured working-hours window/timezone/allowed days
    (Organization's scheduling_* columns, editable from Settings - see
    routes/organization.py) and excluding anything within MIN_LEAD_TIME_HOURS
    of right now. Returns a list of (start, end) naive-UTC datetime tuples,
    ascending.

    Raises CalendarNotConnectedError / CalendarTokenError (from
    get_valid_access_token) or requests.RequestException on a Microsoft
    Graph API failure - callers on a public, candidate-facing page should
    catch these and treat them as "no slots available" rather than a 500;
    see routes/apply.py.
    """
    connection = CalendarConnection.query.filter_by(user_id=user.id).first()
    if not connection:
        raise CalendarNotConnectedError(f'user {user.id} has no connected calendar')
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

    busy_blocks = _get_schedule_request(
        access_token, connection.account_email, candidate_slots[0][0], candidate_slots[-1][1],
    )
    earliest_allowed = datetime.utcnow() + timedelta(hours=MIN_LEAD_TIME_HOURS)

    def _is_free(slot_start, slot_end):
        if slot_start < earliest_allowed:
            return False
        return not any(slot_start < busy_end and slot_end > busy_start for busy_start, busy_end in busy_blocks)

    return [s for s in candidate_slots if _is_free(*s)]


# --- booking ------------------------------------------------------------------

def _create_calendar_event_request(access_token, body):
    """POSTs a new event to the connected user's calendar. Split out from
    create_event so tests can monkeypatch just this - see module
    docstring."""
    resp = requests.post(
        GRAPH_EVENTS_URL,
        headers={'Authorization': f'Bearer {access_token}'},
        json=body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _delete_calendar_event_request(access_token, event_id):
    resp = requests.delete(
        f'{GRAPH_EVENTS_URL}/{event_id}',
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    # 404 means it's already deleted/never existed - fine either way, the
    # caller's goal (no such event remains) is already satisfied.
    if resp.status_code not in (204, 404):
        resp.raise_for_status()


def create_event(user, summary, description, start, end, attendee_email=None, meeting_link=None):
    """Creates a real Microsoft/Outlook Calendar event on `user`'s calendar.
    start/end are naive-UTC datetimes, per this app's storage convention
    (see models.iso_utc). No explicit "notify attendees" flag to set here
    (unlike Google's sendUpdates) - Graph always emails an invite to
    `attendees`, so attendee_email is left off the request; the candidate
    gets their own confirmation email (email_sender.send_confirmation_email)
    instead, to avoid sending two different-looking notifications for the
    same booking.

    Interviews are conducted over RingCentral rather than a link generated
    per-event by the calendar provider (Microsoft Teams, Google Meet, etc.)
    - `meeting_link` is the interviewer's own static link
    (User.personal_meeting_link, read by the caller - see routes/apply.py),
    set as the event's `location` here purely so it's visible on the
    interviewer's own calendar entry. It is NOT returned from here: the
    caller already has it and is the source of truth for
    Interview.meeting_link, since an interviewer can change their link at
    any time independent of already-booked events.

    Returns the created event's id. Raises requests.RequestException on
    failure, and whatever get_valid_access_token raises if the user's
    calendar isn't connected.
    """
    access_token = get_valid_access_token(user)

    body = {
        'subject': summary,
        'body': {'contentType': 'text', 'content': description},
        'start': {'dateTime': iso_utc(start), 'timeZone': 'UTC'},
        'end': {'dateTime': iso_utc(end), 'timeZone': 'UTC'},
    }
    if meeting_link:
        body['location'] = {'displayName': meeting_link}
    # attendees is deliberately omitted when there's no attendee_email - an
    # empty list is fine too, but this keeps the request body minimal for
    # the (currently only theoretical) no-attendee case.
    if attendee_email:
        body['attendees'] = [{'emailAddress': {'address': attendee_email}, 'type': 'required'}]

    event = _create_calendar_event_request(access_token, body)
    return event['id']


def delete_event(user, event_id):
    """Deletes a previously-created event from `user`'s calendar - used as a
    best-effort compensating action if a booking fails to persist on our
    side after the calendar event was already created (see routes/apply.py's
    submit endpoint). Raises the same way create_event does; callers already
    treat this as best-effort and catch broadly."""
    access_token = get_valid_access_token(user)
    _delete_calendar_event_request(access_token, event_id)

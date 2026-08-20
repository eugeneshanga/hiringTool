"""Google OAuth + token-refresh plumbing for calendar integration.

Phase 1 only covers getting a User connected and being able to hand back a
valid access token for them — no availability or booking logic lives here
yet. Everything that later phases (availability windows, booking) need to
call Google's Calendar API goes through get_valid_access_token(), so that's
the one function worth getting right and well-tested here.
"""
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet
from flask import current_app

from models import CalendarConnection, db

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'

# calendar.events is enough to create/read
# events without also granting read/write on calendar *settings* - openid
# email is just so we can label the connection with which Google account it
# is (CalendarConnection.google_email), for display purposes.
CALENDAR_SCOPES = 'openid email https://www.googleapis.com/auth/calendar.events'

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

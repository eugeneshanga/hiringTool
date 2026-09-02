"""Phase 1 of Microsoft Calendar integration: connecting/disconnecting a
User's calendar, and the token-refresh helper every later phase
(availability, booking) will call. Nothing here talks to real Microsoft
Graph APIs - the HTTP calls in microsoft_calendar.py are monkeypatched out."""
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

import routes.calendar_auth as calendar_auth
from microsoft_calendar import CalendarNotConnectedError, decrypt_token, encrypt_token, get_valid_access_token
from models import CalendarConnection, db


def _state_for(app, user_id):
    with app.app_context():
        return calendar_auth._state_serializer().dumps({'user_id': user_id})


# --- connect ------------------------------------------------------------

def test_connect_redirects_to_microsoft_with_signed_state(client, auth_headers, user):
    resp = client.get('/api/auth/microsoft/connect', headers=auth_headers)

    assert resp.status_code == 302
    location = urlparse(resp.headers['Location'])
    assert location.netloc == 'login.microsoftonline.com'
    query = parse_qs(location.query)
    assert query['response_type'] == ['code']
    assert query['prompt'] == ['consent']
    assert 'Calendars.ReadWrite' in query['scope'][0]
    assert 'offline_access' in query['scope'][0]
    assert 'state' in query


def test_connect_requires_auth(client):
    resp = client.get('/api/auth/microsoft/connect')
    assert resp.status_code == 401


# --- callback -------------------------------------------------------------

def test_callback_creates_connection_from_valid_code(app, client, user, monkeypatch):
    monkeypatch.setattr(
        calendar_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'access-123', 'refresh_token': 'refresh-456', 'expires_in': 3600},
    )
    monkeypatch.setattr(calendar_auth, 'fetch_microsoft_email', lambda access_token: 'interviewer@outlook.com')

    state = _state_for(app, user.id)
    resp = client.get(f'/api/auth/microsoft/callback?code=fakecode&state={state}')

    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('?calendar_connected=true')

    with app.app_context():
        connection = CalendarConnection.query.filter_by(user_id=user.id).first()
        assert connection is not None
        assert connection.account_email == 'interviewer@outlook.com'
        assert connection.access_token == 'access-123'
        assert decrypt_token(connection.encrypted_refresh_token) == 'refresh-456'
        assert connection.token_expiry > datetime.utcnow()


def test_callback_upserts_rather_than_duplicating_on_reconnect(app, client, user, monkeypatch):
    monkeypatch.setattr(
        calendar_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'first-token', 'refresh_token': 'first-refresh', 'expires_in': 3600},
    )
    monkeypatch.setattr(calendar_auth, 'fetch_microsoft_email', lambda access_token: 'interviewer@outlook.com')
    client.get(f'/api/auth/microsoft/callback?code=c1&state={_state_for(app, user.id)}')

    monkeypatch.setattr(
        calendar_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'second-token', 'refresh_token': 'second-refresh', 'expires_in': 3600},
    )
    client.get(f'/api/auth/microsoft/callback?code=c2&state={_state_for(app, user.id)}')

    with app.app_context():
        connections = CalendarConnection.query.filter_by(user_id=user.id).all()
        assert len(connections) == 1
        assert connections[0].access_token == 'second-token'
        assert decrypt_token(connections[0].encrypted_refresh_token) == 'second-refresh'


def test_callback_reports_microsoft_denied_consent(client):
    resp = client.get('/api/auth/microsoft/callback?error=access_denied')
    assert resp.status_code == 302
    assert 'calendar_error=access_denied' in resp.headers['Location']


def test_callback_rejects_tampered_state(client):
    resp = client.get('/api/auth/microsoft/callback?code=fakecode&state=not-a-real-signature')
    assert resp.status_code == 302
    assert 'calendar_error=invalid_state' in resp.headers['Location']


def test_callback_reports_token_exchange_failure(app, client, user, monkeypatch):
    def _blow_up(code):
        raise RuntimeError('Microsoft said no')

    monkeypatch.setattr(calendar_auth, 'exchange_code_for_tokens', _blow_up)

    resp = client.get(f'/api/auth/microsoft/callback?code=fakecode&state={_state_for(app, user.id)}')
    assert resp.status_code == 302
    assert 'calendar_error=token_exchange_failed' in resp.headers['Location']

    with app.app_context():
        assert CalendarConnection.query.filter_by(user_id=user.id).first() is None


def test_callback_preserves_existing_refresh_token_when_response_omits_one(app, client, user, monkeypatch):
    """build_authorization_url always sets prompt=consent, so Microsoft
    should issue a refresh_token every callback - but the callback still
    guards against the rare response that omits one, rather than blowing
    away a working refresh token with nothing."""
    with app.app_context():
        db.session.add(CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('still-good-refresh'),
        ))
        db.session.commit()

    monkeypatch.setattr(
        calendar_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'access-123', 'expires_in': 3600},
    )
    monkeypatch.setattr(calendar_auth, 'fetch_microsoft_email', lambda access_token: 'interviewer@outlook.com')

    resp = client.get(f'/api/auth/microsoft/callback?code=fakecode&state={_state_for(app, user.id)}')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('?calendar_connected=true')

    with app.app_context():
        connection = CalendarConnection.query.filter_by(user_id=user.id).first()
        assert decrypt_token(connection.encrypted_refresh_token) == 'still-good-refresh'


# --- disconnect -------------------------------------------------------------

def test_disconnect_removes_the_connection(app, client, auth_headers, user):
    with app.app_context():
        db.session.add(CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
        ))
        db.session.commit()

    resp = client.delete('/api/auth/microsoft/disconnect', headers=auth_headers)
    assert resp.status_code == 204

    with app.app_context():
        assert CalendarConnection.query.filter_by(user_id=user.id).first() is None


def test_disconnect_with_no_connection_is_a_404(client, auth_headers):
    resp = client.delete('/api/auth/microsoft/disconnect', headers=auth_headers)
    assert resp.status_code == 404


def test_status_reflects_connected_state(app, client, auth_headers, user):
    before = client.get('/api/auth/microsoft/status', headers=auth_headers).get_json()
    assert before == {'connected': False}

    with app.app_context():
        db.session.add(CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
        ))
        db.session.commit()

    after = client.get('/api/auth/microsoft/status', headers=auth_headers).get_json()
    assert after == {'connected': True, 'account_email': 'interviewer@outlook.com'}


# --- get_valid_access_token --------------------------------------------------

def test_get_valid_access_token_raises_when_never_connected(app, user):
    with app.app_context():
        with pytest.raises(CalendarNotConnectedError):
            get_valid_access_token(user)


def test_get_valid_access_token_returns_cached_token_without_refreshing(app, user, monkeypatch):
    def _fail_if_called(refresh_token):
        raise AssertionError('should not refresh when the cached token is still valid')

    monkeypatch.setattr('microsoft_calendar._refresh_access_token', _fail_if_called)

    with app.app_context():
        db.session.add(CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
            access_token='still-good', token_expiry=datetime.utcnow() + timedelta(minutes=30),
        ))
        db.session.commit()

        token = get_valid_access_token(user)
        assert token == 'still-good'


def test_get_valid_access_token_refreshes_when_expired(app, user, monkeypatch):
    monkeypatch.setattr(
        'microsoft_calendar._refresh_access_token',
        lambda refresh_token: {'access_token': 'refreshed-token', 'expires_in': 3600},
    )

    with app.app_context():
        connection = CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
            access_token='stale-token', token_expiry=datetime.utcnow() - timedelta(minutes=5),
        )
        db.session.add(connection)
        db.session.commit()

        token = get_valid_access_token(user)
        assert token == 'refreshed-token'

        refreshed = db.session.get(CalendarConnection, connection.id)
        assert refreshed.access_token == 'refreshed-token'
        assert refreshed.token_expiry > datetime.utcnow() + timedelta(minutes=59)


def test_get_valid_access_token_refreshes_when_never_fetched(app, user, monkeypatch):
    """No access_token/token_expiry at all yet - the state right after the
    initial connect if Phase 1's callback ever didn't store one."""
    monkeypatch.setattr(
        'microsoft_calendar._refresh_access_token',
        lambda refresh_token: {'access_token': 'first-real-token', 'expires_in': 1800},
    )

    with app.app_context():
        db.session.add(CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
        ))
        db.session.commit()

        token = get_valid_access_token(user)
        assert token == 'first-real-token'


def test_get_valid_access_token_persists_rotated_refresh_token(app, user, monkeypatch):
    """Unlike Google's stable refresh tokens, Microsoft may rotate the
    refresh token on every use - the new one must be persisted, since the
    old one can stop working once a new one's been issued."""
    monkeypatch.setattr(
        'microsoft_calendar._refresh_access_token',
        lambda refresh_token: {
            'access_token': 'refreshed-token', 'expires_in': 3600, 'refresh_token': 'rotated-refresh',
        },
    )

    with app.app_context():
        connection = CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('original-refresh'),
            access_token='stale-token', token_expiry=datetime.utcnow() - timedelta(minutes=5),
        )
        db.session.add(connection)
        db.session.commit()

        get_valid_access_token(user)

        refreshed = db.session.get(CalendarConnection, connection.id)
        assert decrypt_token(refreshed.encrypted_refresh_token) == 'rotated-refresh'

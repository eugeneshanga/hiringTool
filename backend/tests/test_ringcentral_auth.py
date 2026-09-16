"""RingCentral OAuth connect/callback/disconnect/status - mirrors
test_calendar_auth.py's Microsoft equivalent closely. Nothing here talks to
a real RingCentral API - the HTTP calls in ringcentral_video.py are
monkeypatched out."""
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import routes.ringcentral_auth as ringcentral_auth
from ringcentral_video import decrypt_token
from models import RingCentralConnection, db


def _state_for(app, user_id):
    with app.app_context():
        return ringcentral_auth._state_serializer().dumps({'user_id': user_id})


# --- connect ------------------------------------------------------------

def test_connect_redirects_to_ringcentral_with_signed_state(client, auth_headers, user):
    resp = client.get('/api/auth/ringcentral/connect', headers=auth_headers)

    assert resp.status_code == 302
    location = urlparse(resp.headers['Location'])
    assert location.netloc == 'platform.ringcentral.com'
    query = parse_qs(location.query)
    assert query['response_type'] == ['code']
    assert 'state' in query


def test_connect_requires_auth(client):
    resp = client.get('/api/auth/ringcentral/connect')
    assert resp.status_code == 401


# --- callback -------------------------------------------------------------

def test_callback_creates_connection_from_valid_code(app, client, user, monkeypatch):
    monkeypatch.setattr(
        ringcentral_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'access-123', 'refresh_token': 'refresh-456', 'expires_in': 3600},
    )
    monkeypatch.setattr(ringcentral_auth, 'fetch_ringcentral_email', lambda access_token: 'interviewer@rc.com')

    state = _state_for(app, user.id)
    resp = client.get(f'/api/auth/ringcentral/callback?code=fakecode&state={state}')

    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('?ringcentral_connected=true')

    with app.app_context():
        connection = RingCentralConnection.query.filter_by(user_id=user.id).first()
        assert connection is not None
        assert connection.account_email == 'interviewer@rc.com'
        assert connection.access_token == 'access-123'
        assert decrypt_token(connection.encrypted_refresh_token) == 'refresh-456'
        assert connection.token_expiry > datetime.utcnow()


def test_callback_upserts_rather_than_duplicating_on_reconnect(app, client, user, monkeypatch):
    monkeypatch.setattr(
        ringcentral_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'first-token', 'refresh_token': 'first-refresh', 'expires_in': 3600},
    )
    monkeypatch.setattr(ringcentral_auth, 'fetch_ringcentral_email', lambda access_token: 'interviewer@rc.com')
    state = _state_for(app, user.id)
    client.get(f'/api/auth/ringcentral/callback?code=fakecode&state={state}')

    monkeypatch.setattr(
        ringcentral_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'second-token', 'refresh_token': 'second-refresh', 'expires_in': 3600},
    )
    client.get(f'/api/auth/ringcentral/callback?code=fakecode2&state={state}')

    with app.app_context():
        connections = RingCentralConnection.query.filter_by(user_id=user.id).all()
        assert len(connections) == 1
        assert decrypt_token(connections[0].encrypted_refresh_token) == 'second-refresh'


def test_callback_denied_access_redirects_with_error(app, client, user):
    resp = client.get('/api/auth/ringcentral/callback?error=access_denied')
    assert resp.status_code == 302
    assert 'ringcentral_error=access_denied' in resp.headers['Location']


def test_callback_missing_refresh_token_is_an_error(app, client, user, monkeypatch):
    monkeypatch.setattr(
        ringcentral_auth, 'exchange_code_for_tokens',
        lambda code: {'access_token': 'access-123', 'expires_in': 3600},  # no refresh_token
    )
    monkeypatch.setattr(ringcentral_auth, 'fetch_ringcentral_email', lambda access_token: 'interviewer@rc.com')
    state = _state_for(app, user.id)

    resp = client.get(f'/api/auth/ringcentral/callback?code=fakecode&state={state}')

    assert 'ringcentral_error=no_refresh_token' in resp.headers['Location']
    with app.app_context():
        assert RingCentralConnection.query.filter_by(user_id=user.id).first() is None


def test_callback_invalid_state_is_rejected(client):
    resp = client.get('/api/auth/ringcentral/callback?code=fakecode&state=garbage')
    assert 'ringcentral_error=invalid_state' in resp.headers['Location']


# --- disconnect / status --------------------------------------------------

def test_disconnect_removes_the_connection(app, client, auth_headers, user):
    with app.app_context():
        db.session.add(RingCentralConnection(
            user_id=user.id, account_email='interviewer@rc.com', encrypted_refresh_token='enc',
        ))
        db.session.commit()

    resp = client.delete('/api/auth/ringcentral/disconnect', headers=auth_headers)
    assert resp.status_code == 204
    with app.app_context():
        assert RingCentralConnection.query.filter_by(user_id=user.id).first() is None


def test_disconnect_404s_with_no_existing_connection(client, auth_headers):
    resp = client.delete('/api/auth/ringcentral/disconnect', headers=auth_headers)
    assert resp.status_code == 404


def test_status_reports_connected_state(app, client, auth_headers, user):
    resp = client.get('/api/auth/ringcentral/status', headers=auth_headers)
    assert resp.get_json() == {"connected": False}

    with app.app_context():
        db.session.add(RingCentralConnection(
            user_id=user.id, account_email='interviewer@rc.com', encrypted_refresh_token='enc',
        ))
        db.session.commit()

    resp = client.get('/api/auth/ringcentral/status', headers=auth_headers)
    assert resp.get_json() == {"connected": True, "account_email": "interviewer@rc.com"}

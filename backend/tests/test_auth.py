import pytest
import requests

import routes.auth as auth_module


def test_login_with_valid_credentials(client, user):
    resp = client.post('/api/auth/login', json={'email': user.email, 'password': 'password123'})
    assert resp.status_code == 200
    assert 'access_token' in resp.get_json()


# --- reCAPTCHA (only enforced when RECAPTCHA_SECRET_KEY is configured -
# unset for every other test in this file, and in local dev by default, so
# login behaves exactly as before unless this is explicitly set) ---------

@pytest.fixture
def recaptcha_app(app):
    app.config['RECAPTCHA_SECRET_KEY'] = 'test-secret'
    yield app
    app.config['RECAPTCHA_SECRET_KEY'] = None


def test_login_requires_a_recaptcha_token_when_configured(recaptcha_app, client, user):
    resp = client.post('/api/auth/login', json={'email': user.email, 'password': 'password123'})
    assert resp.status_code == 400
    assert 'recaptcha' in resp.get_json()['error'].lower()


def test_login_succeeds_with_a_verified_recaptcha_token(recaptcha_app, client, user, monkeypatch):
    monkeypatch.setattr(auth_module, 'verify_recaptcha', lambda secret, token, remote_ip=None: True)
    resp = client.post(
        '/api/auth/login',
        json={'email': user.email, 'password': 'password123', 'recaptcha_token': 'good-token'},
    )
    assert resp.status_code == 200


def test_login_rejects_a_failed_recaptcha_verification(recaptcha_app, client, user, monkeypatch):
    monkeypatch.setattr(auth_module, 'verify_recaptcha', lambda secret, token, remote_ip=None: False)
    resp = client.post(
        '/api/auth/login',
        json={'email': user.email, 'password': 'password123', 'recaptcha_token': 'stale-token'},
    )
    assert resp.status_code == 400
    # Never even reaches the credential check - a bot can't use a wrong
    # password to distinguish "no recaptcha" from "recaptcha failed" from
    # "recaptcha ok but wrong password".
    assert 'recaptcha' in resp.get_json()['error'].lower()


def test_login_fails_closed_when_recaptcha_verification_is_unreachable(recaptcha_app, client, user, monkeypatch):
    def _boom(secret, token, remote_ip=None):
        raise requests.ConnectionError('could not reach Google')
    monkeypatch.setattr(auth_module, 'verify_recaptcha', _boom)

    resp = client.post(
        '/api/auth/login',
        json={'email': user.email, 'password': 'password123', 'recaptcha_token': 'good-token'},
    )
    assert resp.status_code == 503


def test_login_rejects_wrong_password(client, user):
    resp = client.post('/api/auth/login', json={'email': user.email, 'password': 'wrong-password'})
    assert resp.status_code == 401


def test_login_rate_limits_repeat_attempts_against_one_email(client, user):
    for _ in range(10):
        client.post('/api/auth/login', json={'email': user.email, 'password': 'wrong-password'})

    resp = client.post('/api/auth/login', json={'email': user.email, 'password': 'wrong-password'})
    assert resp.status_code == 429


def test_login_rate_limit_is_keyed_per_email_not_globally(client, user, admin_user):
    """A credential-stuffing attempt exhausting one email's limit shouldn't
    block a login attempt against a different email from the same IP."""
    for _ in range(10):
        client.post('/api/auth/login', json={'email': user.email, 'password': 'wrong-password'})
    assert client.post(
        '/api/auth/login', json={'email': user.email, 'password': 'wrong-password'},
    ).status_code == 429

    resp = client.post('/api/auth/login', json={'email': admin_user.email, 'password': 'password123'})
    assert resp.status_code == 200


def test_login_rate_limits_by_ip_across_many_emails(client, user):
    """The per-IP cap (20/hour) catches an attacker rotating email guesses
    from one IP, independent of the per-email cap (10/hour, tested above)."""
    for i in range(20):
        client.post('/api/auth/login', json={'email': f'nonexistent-{i}@example.com', 'password': 'guess'})

    resp = client.post('/api/auth/login', json={'email': 'yet-another@example.com', 'password': 'guess'})
    assert resp.status_code == 429


def test_me_requires_auth(client):
    assert client.get('/api/auth/me').status_code == 401


def test_me_returns_current_user(client, auth_headers, user):
    resp = client.get('/api/auth/me', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()['email'] == user.email


def test_update_me_sets_personal_meeting_link(client, auth_headers):
    resp = client.patch(
        '/api/auth/me', headers=auth_headers,
        json={'personal_meeting_link': 'https://v.ringcentral.com/join/199431569'},
    )
    assert resp.status_code == 200
    assert resp.get_json()['personal_meeting_link'] == 'https://v.ringcentral.com/join/199431569'


def test_update_me_rejects_a_link_without_http_scheme(client, auth_headers):
    resp = client.patch(
        '/api/auth/me', headers=auth_headers, json={'personal_meeting_link': 'v.ringcentral.com/join/199431569'},
    )
    assert resp.status_code == 400


def test_update_me_clears_personal_meeting_link_with_an_empty_string(client, auth_headers):
    client.patch(
        '/api/auth/me', headers=auth_headers,
        json={'personal_meeting_link': 'https://v.ringcentral.com/join/199431569'},
    )
    resp = client.patch('/api/auth/me', headers=auth_headers, json={'personal_meeting_link': ''})
    assert resp.status_code == 200
    assert resp.get_json()['personal_meeting_link'] is None

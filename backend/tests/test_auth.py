def test_login_with_valid_credentials(client, user):
    resp = client.post('/api/auth/login', json={'email': user.email, 'password': 'password123'})
    assert resp.status_code == 200
    assert 'access_token' in resp.get_json()


def test_login_rejects_wrong_password(client, user):
    resp = client.post('/api/auth/login', json={'email': user.email, 'password': 'wrong-password'})
    assert resp.status_code == 401


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

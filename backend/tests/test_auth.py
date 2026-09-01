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

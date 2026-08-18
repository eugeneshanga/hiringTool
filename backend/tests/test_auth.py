def test_register_creates_account_and_returns_token(client):
    resp = client.post('/api/auth/register', json={
        'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123',
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert 'access_token' in body
    assert body['user']['email'] == 'jane@example.com'
    assert body['user']['role'] == 'recruiter'  # self-registration can't grant itself elevated roles


def test_register_rejects_duplicate_email(client):
    payload = {'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123'}
    client.post('/api/auth/register', json=payload)
    resp = client.post('/api/auth/register', json=payload)
    assert resp.status_code == 409


def test_register_rejects_short_password(client):
    resp = client.post('/api/auth/register', json={
        'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'short',
    })
    assert resp.status_code == 400


def test_login_with_registered_account(client):
    client.post('/api/auth/register', json={
        'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123',
    })
    resp = client.post('/api/auth/login', json={'email': 'jane@example.com', 'password': 'password123'})
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

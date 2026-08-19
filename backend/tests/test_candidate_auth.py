"""CandidateAccount is a separate login identity from User (recruiter/admin/
interviewer) — a candidate's token must never work on recruiter routes, and
a recruiter's token must never work on candidate routes. That boundary is
enforced by app.py's token_verification_loader, not by anything in these
routes themselves, so it's worth testing directly (see app.py's comment on
why this matters: recruiter routes don't check role at all yet)."""


def test_register_creates_account_and_returns_token(client):
    resp = client.post('/api/candidate-auth/register', json={
        'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123',
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert 'access_token' in body
    assert body['candidate']['email'] == 'jane@example.com'
    assert 'password_hash' not in body['candidate']


def test_register_rejects_duplicate_email(client):
    payload = {'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123'}
    client.post('/api/candidate-auth/register', json=payload)
    resp = client.post('/api/candidate-auth/register', json=payload)
    assert resp.status_code == 409


def test_register_rejects_short_password(client):
    resp = client.post('/api/candidate-auth/register', json={
        'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'short',
    })
    assert resp.status_code == 400


def test_login_and_me(client):
    client.post('/api/candidate-auth/register', json={
        'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123',
    })
    login = client.post('/api/candidate-auth/login', json={'email': 'jane@example.com', 'password': 'password123'})
    assert login.status_code == 200
    token = login.get_json()['access_token']

    me = client.get('/api/candidate/me', headers={'Authorization': f'Bearer {token}'})
    assert me.status_code == 200
    assert me.get_json()['email'] == 'jane@example.com'


def test_login_rejects_wrong_password(client, candidate_account):
    resp = client.post('/api/candidate-auth/login', json={'email': candidate_account.email, 'password': 'wrong'})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    assert client.get('/api/candidate/me').status_code == 401


def test_candidate_token_is_rejected_on_recruiter_routes(client, candidate_auth_headers):
    """The actual security boundary: a candidate token must not work as a
    recruiter session, since recruiter routes don't check role themselves.
    flask-jwt-extended's token_verification_loader rejects with 400 (not
    401/403) when a token fails this kind of custom claims check."""
    resp = client.get('/api/jobs', headers=candidate_auth_headers)
    assert resp.status_code == 400

    resp = client.get('/api/auth/me', headers=candidate_auth_headers)
    assert resp.status_code == 400


def test_recruiter_token_is_rejected_on_candidate_routes(client, auth_headers):
    resp = client.get('/api/candidate/me', headers=auth_headers)
    assert resp.status_code == 400


def test_legacy_token_without_type_claim_still_works_on_recruiter_routes(client, app, user):
    """Tokens issued before the `type` claim existed have none at all —
    verify_token_type must default those to recruiter, not reject them."""
    from flask_jwt_extended import create_access_token

    with app.app_context():
        legacy_token = create_access_token(identity=str(user.id))  # no additional_claims

    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {legacy_token}'})
    assert resp.status_code == 200


def test_registering_adds_candidate_to_recruiter_list(client, auth_headers):
    """A self-registered candidate should show up for recruiters right away,
    unassigned to any job — same as one added by hand."""
    register = client.post('/api/candidate-auth/register', json={
        'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123',
    })
    account_id = register.get_json()['candidate']['id']

    listed = client.get('/api/candidates', headers=auth_headers).get_json()
    matches = [c for c in listed if c['candidate_account_id'] == account_id]
    assert len(matches) == 1
    assert matches[0]['name'] == 'Jane Doe'
    assert matches[0]['email'] == 'jane@example.com'
    assert matches[0]['job_id'] is None


def test_logging_in_does_not_create_a_second_candidate_row(client, auth_headers):
    payload = {'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com', 'password': 'password123'}
    register = client.post('/api/candidate-auth/register', json=payload)
    account_id = register.get_json()['candidate']['id']

    client.post('/api/candidate-auth/login', json={'email': payload['email'], 'password': payload['password']})
    client.post('/api/candidate-auth/login', json={'email': payload['email'], 'password': payload['password']})

    listed = client.get('/api/candidates', headers=auth_headers).get_json()
    matches = [c for c in listed if c['candidate_account_id'] == account_id]
    assert len(matches) == 1

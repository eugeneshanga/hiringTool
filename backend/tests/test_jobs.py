"""Covers validate_job_fields (routes/jobs.py) after its 'status'/'salary_period'
checks were deduped through validation.validate_choice."""


def test_create_job_rejects_invalid_status(client, auth_headers):
    resp = client.post('/api/jobs', headers=auth_headers, json={'title': 'CHHA', 'status': 'Nonsense'})
    assert resp.status_code == 400
    assert 'status' in resp.get_json()['error']


def test_create_job_rejects_invalid_salary_period(client, auth_headers):
    resp = client.post('/api/jobs', headers=auth_headers, json={'title': 'CHHA', 'salary_period': 'Weekly'})
    assert resp.status_code == 400
    assert 'salary_period' in resp.get_json()['error']


def test_create_job_accepts_valid_fields(client, auth_headers):
    resp = client.post('/api/jobs', headers=auth_headers, json={
        'title': 'CHHA', 'status': 'Published', 'salary_period': 'Hourly',
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['status'] == 'Published'
    assert body['salary_period'] == 'Hourly'


def test_update_job_rejects_invalid_status(client, auth_headers, job):
    resp = client.patch(f'/api/jobs/{job.id}', headers=auth_headers, json={'status': 'Nonsense'})
    assert resp.status_code == 400

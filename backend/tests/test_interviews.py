"""Enroll/unenroll + capacity are the trickiest logic in the interviews route
(routes/interviews.py) — this is the "safety net before refactoring" test
the code review called for."""


def create_interview(client, headers, **overrides):
    payload = dict(
        stage_name='Orientation',
        meeting_type='Orientation',
        scheduled_start='2026-09-01T13:00:00.000Z',
        scheduled_end='2026-09-01T14:00:00.000Z',
        capacity=2,
    )
    payload.update(overrides)
    resp = client.post('/api/interviews', headers=headers, json=payload)
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


def test_enroll_fills_capacity_then_rejects_overflow(client, auth_headers, candidate_factory):
    interview = create_interview(client, auth_headers, capacity=1)
    c1 = candidate_factory(email='c1@example.com')
    c2 = candidate_factory(email='c2@example.com')

    r1 = client.post(
        f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': c1.id}
    )
    assert r1.status_code == 200
    assert r1.get_json()['scheduled_count'] == 1

    r2 = client.post(
        f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': c2.id}
    )
    assert r2.status_code == 400
    assert 'capacity' in r2.get_json()['error']


def test_enroll_moves_candidate_to_interview_stage(client, auth_headers, candidate_factory):
    interview = create_interview(client, auth_headers)
    candidate = candidate_factory(stage='Applied')

    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate.id})

    detail = client.get(f'/api/candidates/{candidate.id}', headers=auth_headers).get_json()
    assert detail['stage'] == 'Interview'


def test_enroll_same_candidate_twice_is_rejected(client, auth_headers, candidate_factory):
    interview = create_interview(client, auth_headers, capacity=2)
    candidate = candidate_factory()

    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate.id})
    r2 = client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate.id})

    assert r2.status_code == 400
    assert 'already enrolled' in r2.get_json()['error']


def test_unenroll_frees_up_capacity_for_reenrollment(client, auth_headers, candidate_factory):
    interview = create_interview(client, auth_headers, capacity=1)
    c1 = candidate_factory(email='c1@example.com')
    c2 = candidate_factory(email='c2@example.com')

    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': c1.id})
    client.post(f"/api/interviews/{interview['id']}/unenroll", headers=auth_headers, json={'candidate_id': c1.id})

    r = client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': c2.id})
    assert r.status_code == 200
    assert r.get_json()['scheduled_count'] == 1


def test_capacity_cannot_drop_below_enrolled_count(client, auth_headers, candidate_factory):
    interview = create_interview(client, auth_headers, capacity=2)
    c1 = candidate_factory(email='c1@example.com')
    c2 = candidate_factory(email='c2@example.com')
    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': c1.id})
    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': c2.id})

    r = client.patch(f"/api/interviews/{interview['id']}", headers=auth_headers, json={'capacity': 1})
    assert r.status_code == 400
    assert 'capacity' in r.get_json()['error']


def test_enroll_in_a_stage_session_updates_the_candidates_own_schedule(
    client, auth_headers, candidate_factory, job, meeting_stage
):
    """Enrolling via a session tied to a meeting stage should read the same
    as using "Reschedule" on the candidate's own page — their stages[] entry
    for that template must pick up the status/scheduled_at, not just the
    Interview's candidate list."""
    interview = create_interview(
        client, auth_headers,
        job_id=job.id, meeting_stage_template_id=meeting_stage.id, stage_name=meeting_stage.stage_name,
        meeting_type='Interview',
    )
    candidate = candidate_factory(job_id=job.id)

    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate.id})

    detail = client.get(f'/api/candidates/{candidate.id}', headers=auth_headers).get_json()
    stage = next(s for s in detail['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['status'] == 'Upcoming'
    assert stage['scheduled_at'] == interview['scheduled_start']

    listed = client.get('/api/candidates', headers=auth_headers).get_json()
    listed_candidate = next(c for c in listed if c['id'] == candidate.id)
    assert listed_candidate['current_stage']['scheduled_at'] == interview['scheduled_start']


def test_unenroll_clears_the_candidates_schedule_for_that_stage(
    client, auth_headers, candidate_factory, job, meeting_stage
):
    interview = create_interview(
        client, auth_headers,
        job_id=job.id, meeting_stage_template_id=meeting_stage.id, stage_name=meeting_stage.stage_name,
        meeting_type='Interview',
    )
    candidate = candidate_factory(job_id=job.id)
    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate.id})

    client.post(f"/api/interviews/{interview['id']}/unenroll", headers=auth_headers, json={'candidate_id': candidate.id})

    detail = client.get(f'/api/candidates/{candidate.id}', headers=auth_headers).get_json()
    stage = next(s for s in detail['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['scheduled_at'] is None


def test_unenroll_keeps_schedule_if_still_enrolled_in_another_session_for_the_stage(
    client, auth_headers, candidate_factory, job, meeting_stage
):
    first = create_interview(
        client, auth_headers,
        job_id=job.id, meeting_stage_template_id=meeting_stage.id, stage_name=meeting_stage.stage_name,
        meeting_type='Interview', scheduled_start='2026-09-01T13:00:00.000Z', scheduled_end='2026-09-01T14:00:00.000Z',
    )
    second = create_interview(
        client, auth_headers,
        job_id=job.id, meeting_stage_template_id=meeting_stage.id, stage_name=meeting_stage.stage_name,
        meeting_type='Interview', scheduled_start='2026-09-02T13:00:00.000Z', scheduled_end='2026-09-02T14:00:00.000Z',
    )
    candidate = candidate_factory(job_id=job.id)
    client.post(f"/api/interviews/{first['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate.id})
    client.post(f"/api/interviews/{second['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate.id})

    client.post(f"/api/interviews/{first['id']}/unenroll", headers=auth_headers, json={'candidate_id': candidate.id})

    detail = client.get(f'/api/candidates/{candidate.id}', headers=auth_headers).get_json()
    stage = next(s for s in detail['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['scheduled_at'] == second['scheduled_start']


def test_scheduled_time_round_trips_as_utc(client, auth_headers):
    """Regression test for the tz bug fixed earlier: a time sent with an
    explicit UTC 'Z' must come back with one too, unchanged."""
    interview = create_interview(
        client, auth_headers,
        scheduled_start='2026-08-21T20:21:00.000Z',
        scheduled_end='2026-08-21T21:00:00.000Z',
    )
    assert interview['scheduled_start'] == '2026-08-21T20:21:00Z'
    assert interview['scheduled_end'] == '2026-08-21T21:00:00Z'

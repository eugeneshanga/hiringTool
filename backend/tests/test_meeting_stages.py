"""Interview.stage_name is a denormalized display copy of
MeetingStageTemplate.stage_name, kept in sync via the meeting_stage_template_id
FK (see code review item 4) — renaming a template must cascade into every
linked Interview row, or those sessions silently vanish from the stage's
"Sessions" list."""


def test_renaming_stage_cascades_to_linked_sessions(client, auth_headers, job, meeting_stage):
    interview = client.post('/api/interviews', headers=auth_headers, json={
        'job_id': job.id,
        'meeting_stage_template_id': meeting_stage.id,
        'stage_name': meeting_stage.stage_name,
        'meeting_type': 'Interview',
        'scheduled_start': '2026-09-01T13:00:00.000Z',
        'scheduled_end': '2026-09-01T14:00:00.000Z',
    }).get_json()

    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}',
        headers=auth_headers, json={'stage_name': 'Renamed Stage'},
    )
    assert resp.status_code == 200
    assert resp.get_json()['stage_name'] == 'Renamed Stage'

    updated = client.get(f"/api/interviews/{interview['id']}", headers=auth_headers).get_json()
    assert updated['stage_name'] == 'Renamed Stage'
    assert updated['meeting_stage_template_id'] == meeting_stage.id


def test_renaming_stage_does_not_touch_unlinked_sessions(client, auth_headers, job, meeting_stage):
    # Same job, same name by coincidence, but never linked via the FK — an
    # ad-hoc interview created without picking a stage template.
    unlinked_interview = client.post('/api/interviews', headers=auth_headers, json={
        'job_id': job.id,
        'stage_name': meeting_stage.stage_name,
        'meeting_type': 'Interview',
        'scheduled_start': '2026-09-01T13:00:00.000Z',
        'scheduled_end': '2026-09-01T14:00:00.000Z',
    }).get_json()
    assert unlinked_interview['meeting_stage_template_id'] is None

    client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}',
        headers=auth_headers, json={'stage_name': 'Renamed Stage'},
    )

    unchanged = client.get(f"/api/interviews/{unlinked_interview['id']}", headers=auth_headers).get_json()
    assert unchanged['stage_name'] == meeting_stage.stage_name


def test_create_interview_rejects_stage_template_from_a_different_job(client, auth_headers, job, meeting_stage):
    other_job = client.post('/api/jobs', headers=auth_headers, json={'title': 'Other Job'}).get_json()
    resp = client.post('/api/interviews', headers=auth_headers, json={
        'job_id': other_job['id'],
        'meeting_stage_template_id': meeting_stage.id,  # belongs to `job`, not `other_job`
        'stage_name': meeting_stage.stage_name,
        'meeting_type': 'Interview',
        'scheduled_start': '2026-09-01T13:00:00.000Z',
        'scheduled_end': '2026-09-01T14:00:00.000Z',
    })
    assert resp.status_code == 400


def test_move_reorders_stages(client, auth_headers, job, meeting_stage):
    second = client.post(f'/api/jobs/{job.id}/meeting-stages', headers=auth_headers, json={
        'meeting_type': 'In-person orientation', 'stage_name': 'Orientation',
    }).get_json()

    resp = client.patch(
        f"/api/jobs/{job.id}/meeting-stages/{second['id']}/move", headers=auth_headers, json={'direction': 'up'}
    )
    assert resp.status_code == 200
    ordered = resp.get_json()
    assert [t['id'] for t in ordered] == [second['id'], meeting_stage.id]


def test_scheduling_window_days_defaults_and_updates(client, auth_headers, job, meeting_stage):
    initial = client.get(f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers).get_json()
    assert initial['scheduling_window_days'] == 7

    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers,
        json={'scheduling_window_days': 14},
    )
    assert resp.status_code == 200
    assert resp.get_json()['scheduling_window_days'] == 14


def test_scheduling_window_days_rejects_negative(client, auth_headers, job, meeting_stage):
    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers,
        json={'scheduling_window_days': -1},
    )
    assert resp.status_code == 400


def test_create_in_person_orientation_stores_capacity_and_address(client, auth_headers, job):
    resp = client.post(f'/api/jobs/{job.id}/meeting-stages', headers=auth_headers, json={
        'meeting_type': 'In-person orientation',
        'stage_name': 'Orientation',
        'default_capacity': 4,
        'location': '123 Main St',
        'instructions': 'Ask for the front desk.',
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['default_capacity'] == 4
    assert body['location'] == '123 Main St'
    assert body['instructions'] == 'Ask for the front desk.'


def test_create_stage_rejects_non_positive_default_capacity(client, auth_headers, job):
    resp = client.post(f'/api/jobs/{job.id}/meeting-stages', headers=auth_headers, json={
        'meeting_type': 'In-person orientation', 'stage_name': 'Orientation', 'default_capacity': 0,
    })
    assert resp.status_code == 400
    assert 'default_capacity' in resp.get_json()['error']


def test_create_stage_blank_location_and_instructions_store_as_null(client, auth_headers, job):
    """Mirrors how Candidate/Job routes elsewhere in the app treat an
    empty-string optional field as "not set" rather than storing whitespace."""
    resp = client.post(f'/api/jobs/{job.id}/meeting-stages', headers=auth_headers, json={
        'meeting_type': 'In-person interview', 'stage_name': 'Onsite', 'location': '   ', 'instructions': '',
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['location'] is None
    assert body['instructions'] is None


def test_update_stage_patches_capacity_and_address(client, auth_headers, job, meeting_stage):
    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers,
        json={'default_capacity': 6, 'location': '456 Oak Ave', 'instructions': 'Park in the back.'},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['default_capacity'] == 6
    assert body['location'] == '456 Oak Ave'
    assert body['instructions'] == 'Park in the back.'

    # Clearing it back out (null / empty string) must actually clear it, not
    # leave the previous value stuck.
    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers,
        json={'default_capacity': None, 'location': ''},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['default_capacity'] is None
    assert body['location'] is None


def test_update_stage_sets_interviewer(client, auth_headers, job, meeting_stage, user):
    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers,
        json={'interviewer_user_id': user.id},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['interviewer_user_id'] == user.id
    assert body['interviewer_name'] == user.name

    # Unassigning (null) must actually clear it.
    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers,
        json={'interviewer_user_id': None},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['interviewer_user_id'] is None
    assert body['interviewer_name'] is None


def test_update_stage_rejects_unknown_interviewer(client, auth_headers, job, meeting_stage):
    resp = client.patch(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}', headers=auth_headers,
        json={'interviewer_user_id': 999999},
    )
    assert resp.status_code == 400


def test_available_meeting_stages_include_capacity_and_address(client, auth_headers, job):
    other_job = client.post('/api/jobs', headers=auth_headers, json={'title': 'Other Job'}).get_json()
    client.post(f"/api/jobs/{other_job['id']}/meeting-stages", headers=auth_headers, json={
        'meeting_type': 'In-person orientation', 'stage_name': 'Orientation',
        'default_capacity': 5, 'location': '789 Elm St', 'instructions': 'Bring ID.',
    })

    resp = client.get(f'/api/jobs/{job.id}/meeting-stages/available', headers=auth_headers)
    assert resp.status_code == 200
    option = next(o for o in resp.get_json() if o['stage_name'] == 'Orientation')
    assert option['default_capacity'] == 5
    assert option['location'] == '789 Elm St'
    assert option['instructions'] == 'Bring ID.'

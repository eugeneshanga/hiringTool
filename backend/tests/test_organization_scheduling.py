"""PATCH /api/organization's scheduling_* fields - the working-hours window/
timezone/allowed days microsoft_calendar.get_free_slots reads (see
test_calendar_availability.py for that side). Editing is admin-only, same as
the org name/logo/banner - see admin_headers/auth_headers in conftest.py.
"""


def test_get_organization_includes_scheduling_defaults(client, auth_headers):
    resp = client.get('/api/organization', headers=auth_headers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['scheduling_timezone'] == 'UTC'
    assert data['scheduling_working_hours_start'] == 9
    assert data['scheduling_working_hours_end'] == 17
    assert data['scheduling_days'] == [0, 1, 2, 3, 4]


def test_update_scheduling_settings(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={
        'scheduling_timezone': 'America/New_York',
        'scheduling_working_hours_start': 8,
        'scheduling_working_hours_end': 16,
        'scheduling_days': [0, 2, 4],
    })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['scheduling_timezone'] == 'America/New_York'
    assert data['scheduling_working_hours_start'] == 8
    assert data['scheduling_working_hours_end'] == 16
    assert data['scheduling_days'] == [0, 2, 4]


def test_update_scheduling_settings_requires_admin(client, auth_headers):
    resp = client.patch('/api/organization', headers=auth_headers, json={'scheduling_timezone': 'America/New_York'})
    assert resp.status_code == 403


def test_rejects_unrecognized_timezone(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={'scheduling_timezone': 'Not/A_Zone'})
    assert resp.status_code == 400


def test_rejects_empty_timezone(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={'scheduling_timezone': '  '})
    assert resp.status_code == 400


def test_rejects_start_time_not_before_end_time(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={
        'scheduling_working_hours_start': 17, 'scheduling_working_hours_end': 9,
    })
    assert resp.status_code == 400


def test_rejects_out_of_range_hours(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={
        'scheduling_working_hours_start': 9, 'scheduling_working_hours_end': 24,
    })
    assert resp.status_code == 400


def test_rejects_empty_scheduling_days(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={'scheduling_days': []})
    assert resp.status_code == 400


def test_rejects_out_of_range_scheduling_days(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={'scheduling_days': [0, 7]})
    assert resp.status_code == 400


def test_scheduling_days_are_deduped_and_sorted(client, admin_headers):
    resp = client.patch('/api/organization', headers=admin_headers, json={'scheduling_days': [4, 0, 4, 2]})

    assert resp.status_code == 200
    assert resp.get_json()['scheduling_days'] == [0, 2, 4]


def test_partial_update_leaves_other_scheduling_fields_untouched(client, admin_headers):
    client.patch('/api/organization', headers=admin_headers, json={'scheduling_working_hours_start': 10})

    resp = client.patch('/api/organization', headers=admin_headers, json={'name': 'Renamed Org'})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['name'] == 'Renamed Org'
    assert data['scheduling_working_hours_start'] == 10  # untouched by the name-only update

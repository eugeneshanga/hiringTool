"""GET /api/status: public lookup of a booked interview by confirmation code
or phone number. See routes/status.py's module docstring for why phone
lookups are scoped to only interviews actually booked through the public
apply flow (Interview.confirmation_code IS NOT NULL).
"""
from datetime import datetime, timedelta

import pytest

from models import Candidate, Interview, db


def _book(app, job, *, phone='555-123-4567', confirmation_code='ABC234XYZ', scheduled_start=None, public=True):
    """Creates a Candidate + Interview as if booked (or not) through the
    public apply flow. public=False mimics a recruiter-created interview -
    no confirmation_code - to verify phone lookups never surface those."""
    scheduled_start = scheduled_start or (datetime.utcnow() + timedelta(days=2))
    with app.app_context():
        candidate = Candidate(name='Jane Applicant', email='jane@example.com', job_id=job.id, phone=phone)
        db.session.add(candidate)
        db.session.commit()

        interview = Interview(
            job_id=job.id, stage_name='Virtual interview', meeting_type='Interview',
            scheduled_start=scheduled_start, scheduled_end=scheduled_start + timedelta(minutes=20),
            confirmation_code=(confirmation_code if public else None),
            meeting_link='https://meet.google.com/abc-defg-hij',
        )
        interview.candidates.append(candidate)
        db.session.add(interview)
        db.session.commit()
        return candidate.id, interview.id


def test_requires_code_or_phone(client):
    resp = client.get('/api/status')
    assert resp.status_code == 400


def test_lookup_by_code_returns_booking_details(app, client, job):
    _book(app, job, confirmation_code='ABC234XYZ')

    resp = client.get('/api/status?code=ABC234XYZ')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['candidate_name'] == 'Jane Applicant'
    assert data['job_title'] == job.title
    assert data['stage_name'] == 'Virtual interview'
    assert data['meeting_link'] == 'https://meet.google.com/abc-defg-hij'
    assert data['confirmation_code'] == 'ABC234XYZ'


def test_lookup_by_unknown_code_returns_404(client):
    resp = client.get('/api/status?code=DOESNOTEXIST')
    assert resp.status_code == 404


def test_lookup_by_phone_normalizes_formatting(app, client, job):
    _book(app, job, phone='555-123-4567', confirmation_code='ABC234XYZ')

    resp = client.get('/api/status?phone=(555) 123-4567')

    assert resp.status_code == 200
    assert resp.get_json()['confirmation_code'] == 'ABC234XYZ'


def test_lookup_by_phone_with_country_code_prefix_matches(app, client, job):
    _book(app, job, phone='555-123-4567', confirmation_code='ABC234XYZ')

    resp = client.get('/api/status?phone=1-555-123-4567')

    assert resp.status_code == 200


def test_lookup_by_phone_never_surfaces_a_non_public_interview(app, client, job):
    _book(app, job, phone='555-999-0000', public=False)

    resp = client.get('/api/status?phone=555-999-0000')

    assert resp.status_code == 404


def test_lookup_by_too_short_phone_returns_404(client):
    resp = client.get('/api/status?phone=555')
    assert resp.status_code == 404


def test_lookup_by_phone_prefers_soonest_upcoming_booking(app, client, job):
    _book(
        app, job, phone='555-123-4567', confirmation_code='PAST234XY',
        scheduled_start=datetime.utcnow() - timedelta(days=10),
    )
    _book(
        app, job, phone='555-123-4567', confirmation_code='FUT234XYZ',
        scheduled_start=datetime.utcnow() + timedelta(days=3),
    )

    resp = client.get('/api/status?phone=555-123-4567')

    assert resp.status_code == 200
    assert resp.get_json()['confirmation_code'] == 'FUT234XYZ'


def test_rate_limits_repeat_lookups_by_ip(client):
    for _ in range(20):
        client.get('/api/status?code=nonexistent')

    resp = client.get('/api/status?code=nonexistent')

    assert resp.status_code == 429

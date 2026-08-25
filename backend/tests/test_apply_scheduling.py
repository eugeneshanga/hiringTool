"""GET /api/apply/<token> and POST /api/apply/<token>/submit: the scheduling
page and the atomic booking step. Screening questions are answered earlier,
as part of POST /api/apply itself (see test_apply.py) - a token is only ever
issued to a candidate whose answers already qualified them, so nothing here
deals with screening questions at all. Google Calendar itself is always
mocked at the routes.apply level (get_free_slots/create_event/delete_event)
- see test_calendar_availability.py for coverage of google_calendar.py's own
logic against those same seams.
"""
from datetime import datetime, timedelta

import pytest

import routes.apply as apply_module
from google_calendar import CalendarNotConnectedError, encrypt_token
from models import (
    Candidate,
    CandidateStageProgress,
    CalendarConnection,
    Interview,
    MeetingStageTemplate,
    db,
    iso_utc,
)

FAR_FUTURE = datetime(2035, 1, 1, 9, 0)


@pytest.fixture
def schedulable_stage(app, meeting_stage, user):
    """meeting_stage (from conftest) with an interviewer assigned and that
    interviewer's calendar connected - the state _scheduling_stage_for/
    _available_slots_for_stage need to consider a stage bookable."""
    with app.app_context():
        stage = MeetingStageTemplate.query.get(meeting_stage.id)
        stage.interviewer_user_id = user.id
        db.session.add(CalendarConnection(
            user_id=user.id, google_email='interviewer@gmail.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
            access_token='valid-access-token', token_expiry=datetime.utcnow() + timedelta(minutes=30),
        ))
        db.session.commit()
        db.session.refresh(stage)
        return stage


@pytest.fixture
def applied_candidate(app, job):
    """A candidate who already passed screening (or applied to a job with
    none) and has a live token - i.e. exactly what POST /api/apply leaves
    behind for a qualified candidate. See test_apply.py for how that
    qualification decision itself gets made."""
    with app.app_context():
        candidate = Candidate(
            name='Jane Applicant', email='jane@example.com', job_id=job.id,
            application_token='live-token-abc', application_token_expires_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add(candidate)
        db.session.commit()
        db.session.refresh(candidate)
        return candidate


@pytest.fixture(autouse=True)
def mock_confirmation_email(monkeypatch):
    calls = []
    monkeypatch.setattr(apply_module, 'send_confirmation_email', lambda **kwargs: calls.append(kwargs) or True)
    return calls


# --- GET /api/apply/<token> ---------------------------------------------------

def test_get_application_404_for_unknown_token(client):
    resp = client.get('/api/apply/no-such-token')
    assert resp.status_code == 404


def test_get_application_410_for_expired_token(app, client, job):
    with app.app_context():
        db.session.add(Candidate(
            name='Jane', email='jane@example.com', job_id=job.id,
            application_token='expired-token', application_token_expires_at=datetime.utcnow() - timedelta(days=1),
        ))
        db.session.commit()

    resp = client.get('/api/apply/expired-token')
    assert resp.status_code == 410


def test_get_application_returns_stage_and_slots(app, client, applied_candidate, schedulable_stage, monkeypatch):
    fixed_slots = [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))]
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: fixed_slots)

    resp = client.get(f'/api/apply/{applied_candidate.application_token}')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['already_scheduled'] is False
    assert data['stage_name'] == schedulable_stage.stage_name
    assert data['meeting_type'] == schedulable_stage.meeting_type
    assert data['duration_minutes'] == schedulable_stage.duration_minutes
    assert data['organization_name']  # falls back to a generic phrase if unset - just needs to be present
    assert 'screening_questions' not in data  # answered earlier, at apply time - see test_apply.py
    assert data['available_slots'] == [{"start": iso_utc(FAR_FUTURE), "end": iso_utc(FAR_FUTURE + timedelta(minutes=20))}]


def test_get_application_no_stage_yet_returns_empty_slots(app, client, job):
    with app.app_context():
        candidate = Candidate(
            name='Jane', email='jane@example.com', job_id=job.id,
            application_token='no-stage-token', application_token_expires_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add(candidate)
        db.session.commit()

    resp = client.get('/api/apply/no-stage-token')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['stage_name'] is None
    assert data['available_slots'] == []


def test_get_application_calendar_error_returns_empty_slots_not_500(app, client, applied_candidate, schedulable_stage, monkeypatch):
    def _boom(*a, **k):
        raise CalendarNotConnectedError('nope')

    monkeypatch.setattr(apply_module, 'get_free_slots', _boom)

    resp = client.get(f'/api/apply/{applied_candidate.application_token}')

    assert resp.status_code == 200
    assert resp.get_json()['available_slots'] == []


def test_get_application_already_scheduled_has_no_slots(app, client, applied_candidate, job):
    with app.app_context():
        c = Candidate.query.get(applied_candidate.id)
        c.scheduled = True
        db.session.commit()

    resp = client.get(f'/api/apply/{applied_candidate.application_token}')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['job_title'] == job.title
    assert data['already_scheduled'] is True
    assert 'available_slots' not in data


def test_get_application_already_scheduled_includes_the_booked_interview(
    app, client, applied_candidate, schedulable_stage, monkeypatch,
):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))])
    monkeypatch.setattr(apply_module, 'create_event', lambda *a, **k: ('google-event-9', 'https://meet.google.com/xyz'))

    submit_resp = client.post(f'/api/apply/{applied_candidate.application_token}/submit', json=_submit_payload())
    confirmation_code = submit_resp.get_json()['confirmation_code']

    resp = client.get(f'/api/apply/{applied_candidate.application_token}')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['already_scheduled'] is True
    assert data['stage_name'] == schedulable_stage.stage_name
    assert data['meeting_link'] == 'https://meet.google.com/xyz'
    assert data['confirmation_code'] == confirmation_code
    assert data['scheduled_start'] == iso_utc(FAR_FUTURE)


# --- POST /api/apply/<token>/submit ---------------------------------------------

def _submit_payload(**overrides):
    defaults = {
        "slot_start": iso_utc(FAR_FUTURE),
        "slot_end": iso_utc(FAR_FUTURE + timedelta(minutes=20)),
    }
    defaults.update(overrides)
    return defaults


def test_submit_404_for_unknown_token(client):
    resp = client.post('/api/apply/no-such-token/submit', json=_submit_payload())
    assert resp.status_code == 404


def test_submit_409_when_already_scheduled(app, client, applied_candidate):
    with app.app_context():
        c = Candidate.query.get(applied_candidate.id)
        c.scheduled = True
        db.session.commit()

    resp = client.post(f'/api/apply/{applied_candidate.application_token}/submit', json=_submit_payload())
    assert resp.status_code == 409


def test_submit_400_when_job_has_no_schedulable_stage(client, applied_candidate):
    resp = client.post(f'/api/apply/{applied_candidate.application_token}/submit', json=_submit_payload())
    assert resp.status_code == 400


def test_submit_409_when_slot_is_no_longer_available(app, client, applied_candidate, schedulable_stage, monkeypatch):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [])  # nothing free anymore

    resp = client.post(f'/api/apply/{applied_candidate.application_token}/submit', json=_submit_payload())

    assert resp.status_code == 409


def test_submit_503_when_calendar_event_creation_fails(app, client, applied_candidate, schedulable_stage, monkeypatch):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))])

    def _boom(*a, **k):
        raise RuntimeError('google is down')

    monkeypatch.setattr(apply_module, 'create_event', _boom)

    resp = client.post(f'/api/apply/{applied_candidate.application_token}/submit', json=_submit_payload())

    assert resp.status_code == 503
    with app.app_context():
        assert Interview.query.count() == 0
        assert not Candidate.query.get(applied_candidate.id).scheduled


def test_submit_success_books_everything_and_sends_confirmation(
    app, client, applied_candidate, schedulable_stage, monkeypatch, mock_confirmation_email,
):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))])
    monkeypatch.setattr(apply_module, 'create_event', lambda *a, **k: ('google-event-1', 'https://meet.google.com/abc-defg-hij'))

    resp = client.post(f'/api/apply/{applied_candidate.application_token}/submit', json=_submit_payload())

    assert resp.status_code == 201
    body = resp.get_json()
    assert body['meeting_link'] == 'https://meet.google.com/abc-defg-hij'
    assert len(body['confirmation_code']) == 9

    with app.app_context():
        candidate = Candidate.query.get(applied_candidate.id)
        assert candidate.scheduled is True
        assert candidate.stage == 'Interview'

        interview = Interview.query.filter_by(google_event_id='google-event-1').first()
        assert interview is not None
        assert interview.confirmation_code == body['confirmation_code']
        assert interview.meeting_link == 'https://meet.google.com/abc-defg-hij'
        assert candidate in interview.candidates

        progress = CandidateStageProgress.query.filter_by(
            candidate_id=candidate.id, meeting_stage_template_id=schedulable_stage.id,
        ).first()
        assert progress is not None
        assert progress.status == 'Upcoming'

    assert len(mock_confirmation_email) == 1
    assert mock_confirmation_email[0]['confirmation_code'] == body['confirmation_code']
    assert mock_confirmation_email[0]['to_email'] == 'jane@example.com'


def test_submit_db_failure_after_booking_cleans_up_the_calendar_event(
    app, client, applied_candidate, schedulable_stage, monkeypatch,
):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))])
    monkeypatch.setattr(apply_module, 'create_event', lambda *a, **k: ('google-event-2', 'https://meet.google.com/xyz'))

    deleted = []
    monkeypatch.setattr(apply_module, 'delete_event', lambda user, event_id: deleted.append(event_id))

    def _boom_commit():
        raise RuntimeError('db exploded')

    monkeypatch.setattr(apply_module.db.session, 'commit', _boom_commit)

    resp = client.post(f'/api/apply/{applied_candidate.application_token}/submit', json=_submit_payload())

    assert resp.status_code == 500
    assert deleted == ['google-event-2']

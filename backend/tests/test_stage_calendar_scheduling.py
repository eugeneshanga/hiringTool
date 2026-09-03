"""GET/POST .../available-slots and .../book - a recruiter-initiated
equivalent of the public apply flow's own booking (routes/apply.py), for
scheduling a candidate directly from their detail page against a stage's
real calendar availability. Microsoft Calendar itself is always mocked:
get_free_slots is patched on routes.apply (routes.candidates calls it only
indirectly, via apply.py's own _available_slots_for_stage), while
create_event/delete_event are patched directly on routes.candidates, which
imports and calls them itself."""
from datetime import datetime, timedelta

import pytest

import routes.apply as apply_module
import routes.candidates as candidates_module
from microsoft_calendar import CalendarNotConnectedError, encrypt_token
from models import Candidate, CandidateStageProgress, CalendarConnection, Interview, MeetingStageTemplate, User, db

FAR_FUTURE = datetime(2035, 1, 1, 9, 0)


@pytest.fixture
def schedulable_stage(app, meeting_stage, user):
    """meeting_stage (from conftest) with an interviewer assigned, a
    connected calendar, and a personal meeting link - the state
    get_available_slots/book_stage_slot need to consider a stage bookable."""
    with app.app_context():
        stage = MeetingStageTemplate.query.get(meeting_stage.id)
        stage.interviewer_user_id = user.id
        interviewer = User.query.get(user.id)
        interviewer.personal_meeting_link = 'https://v.ringcentral.com/join/199431569'
        db.session.add(CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
            access_token='valid-access-token', token_expiry=datetime.utcnow() + timedelta(minutes=30),
        ))
        db.session.commit()
        db.session.refresh(stage)
        return stage


@pytest.fixture
def candidate(app, job):
    with app.app_context():
        c = Candidate(name='Jane Applicant', email='jane@example.com', job_id=job.id)
        db.session.add(c)
        db.session.commit()
        db.session.refresh(c)
        return c


@pytest.fixture(autouse=True)
def mock_confirmation_email(monkeypatch):
    calls = []
    monkeypatch.setattr('routes.candidates.send_confirmation_email', lambda **kwargs: calls.append(kwargs) or True)
    return calls


# --- GET .../available-slots ---------------------------------------------------

def test_available_slots_requires_auth(client, candidate, meeting_stage):
    resp = client.get(f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/available-slots')
    assert resp.status_code == 401


def test_available_slots_empty_when_stage_not_set_up(client, auth_headers, candidate, meeting_stage):
    """No interviewer/duration assigned yet - same graceful degradation as
    the public apply flow, not a 500."""
    resp = client.get(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/available-slots', headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()['available_slots'] == []


def test_available_slots_returns_live_slots(app, client, auth_headers, candidate, schedulable_stage, monkeypatch):
    fixed_slots = [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))]
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: fixed_slots)

    resp = client.get(
        f'/api/candidates/{candidate.id}/stages/{schedulable_stage.id}/available-slots', headers=auth_headers,
    )
    assert resp.status_code == 200
    from models import iso_utc
    assert resp.get_json()['available_slots'] == [
        {"start": iso_utc(FAR_FUTURE), "end": iso_utc(FAR_FUTURE + timedelta(minutes=20))}
    ]


def test_available_slots_rejects_stage_from_a_different_job(app, client, auth_headers, candidate):
    with app.app_context():
        from models import Job
        other_job = Job(title='LPN', status='Published')
        db.session.add(other_job)
        db.session.commit()
        other_stage = MeetingStageTemplate(
            job_id=other_job.id, meeting_type='Virtual interview', stage_name='LPN Interview',
            duration_minutes=20, sort_order=0,
        )
        db.session.add(other_stage)
        db.session.commit()
        other_stage_id = other_stage.id

    resp = client.get(
        f'/api/candidates/{candidate.id}/stages/{other_stage_id}/available-slots', headers=auth_headers,
    )
    assert resp.status_code == 400


# --- POST .../book ---------------------------------------------------------------

def _book_payload(**overrides):
    from models import iso_utc
    defaults = {"slot_start": iso_utc(FAR_FUTURE), "slot_end": iso_utc(FAR_FUTURE + timedelta(minutes=20))}
    defaults.update(overrides)
    return defaults


def test_book_400_when_stage_not_set_up(client, auth_headers, candidate, meeting_stage):
    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/book', headers=auth_headers,
        json=_book_payload(),
    )
    assert resp.status_code == 400


def test_book_409_when_slot_no_longer_available(client, auth_headers, candidate, schedulable_stage, monkeypatch):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [])
    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{schedulable_stage.id}/book', headers=auth_headers,
        json=_book_payload(),
    )
    assert resp.status_code == 409


def test_book_creates_a_real_interview_and_calendar_event(
    app, client, auth_headers, candidate, schedulable_stage, monkeypatch, mock_confirmation_email,
):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))])
    monkeypatch.setattr(candidates_module, 'create_event', lambda *a, **k: 'ms-event-1')

    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{schedulable_stage.id}/book', headers=auth_headers,
        json=_book_payload(),
    )

    assert resp.status_code == 200
    body = resp.get_json()
    stage = next(s for s in body['stages'] if s['meeting_stage_template_id'] == schedulable_stage.id)
    assert stage['status'] == 'Upcoming'

    with app.app_context():
        interview = Interview.query.filter_by(calendar_event_id='ms-event-1').first()
        assert interview is not None
        assert interview.meeting_link == 'https://v.ringcentral.com/join/199431569'
        assert candidate.id in [c.id for c in interview.candidates]

        progress = CandidateStageProgress.query.filter_by(
            candidate_id=candidate.id, meeting_stage_template_id=schedulable_stage.id,
        ).first()
        assert progress.status == 'Upcoming'

    assert len(mock_confirmation_email) == 1


def test_rebooking_updates_the_existing_interview_in_place(
    app, client, auth_headers, candidate, schedulable_stage, monkeypatch,
):
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))])
    monkeypatch.setattr(candidates_module, 'create_event', lambda *a, **k: 'ms-event-1')
    client.post(
        f'/api/candidates/{candidate.id}/stages/{schedulable_stage.id}/book', headers=auth_headers,
        json=_book_payload(),
    )
    with app.app_context():
        first_confirmation_code = Interview.query.filter_by(calendar_event_id='ms-event-1').first().confirmation_code

    later = FAR_FUTURE + timedelta(days=1)
    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(later, later + timedelta(minutes=20))])
    monkeypatch.setattr(candidates_module, 'create_event', lambda *a, **k: 'ms-event-2')
    deleted = []
    monkeypatch.setattr(candidates_module, 'delete_event', lambda user, event_id: deleted.append(event_id))

    from models import iso_utc
    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{schedulable_stage.id}/book', headers=auth_headers,
        json={"slot_start": iso_utc(later), "slot_end": iso_utc(later + timedelta(minutes=20))},
    )
    assert resp.status_code == 200
    assert deleted == ['ms-event-1']

    with app.app_context():
        interviews = Interview.query.filter_by(meeting_stage_template_id=schedulable_stage.id).all()
        assert len(interviews) == 1  # updated in place, not a second row
        assert interviews[0].calendar_event_id == 'ms-event-2'
        assert interviews[0].confirmation_code == first_confirmation_code  # stays stable across a reschedule


def test_book_leaves_candidate_stage_untouched(app, client, auth_headers, candidate, schedulable_stage, monkeypatch):
    with app.app_context():
        c = Candidate.query.get(candidate.id)
        c.stage = 'Offer'
        db.session.commit()

    monkeypatch.setattr(apply_module, 'get_free_slots', lambda *a, **k: [(FAR_FUTURE, FAR_FUTURE + timedelta(minutes=20))])
    monkeypatch.setattr(candidates_module, 'create_event', lambda *a, **k: 'ms-event-1')

    client.post(
        f'/api/candidates/{candidate.id}/stages/{schedulable_stage.id}/book', headers=auth_headers,
        json=_book_payload(),
    )

    with app.app_context():
        assert Candidate.query.get(candidate.id).stage == 'Offer'

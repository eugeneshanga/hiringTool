"""PUT /api/candidates/<id>/stages/<template_id> - the recruiter-facing
status/notes/scorecard update, and specifically the 'No' status's cascade
onto Candidate.stage/disqualified_at (mirrors the auto-disqualification
path in routes/apply.py - see scheduled_jobs.py, which picks up
disqualified_at regardless of which path set it)."""
from datetime import datetime, timedelta

import pytest

import routes.apply as apply_module
from models import Candidate, CandidateStageProgress, MeetingStageTemplate, db


@pytest.fixture
def candidate(app, job):
    with app.app_context():
        c = Candidate(name='Jane Applicant', email='jane@example.com', job_id=job.id, stage='Interview')
        db.session.add(c)
        db.session.commit()
        db.session.refresh(c)
        return c


def test_update_stage_progress_requires_auth(client, candidate, meeting_stage):
    resp = client.put(f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', json={'status': 'Needs review'})
    assert resp.status_code == 401


def test_update_stage_progress_sets_status(client, auth_headers, candidate, meeting_stage):
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Needs review'},
    )
    assert resp.status_code == 200
    stage = next(s for s in resp.get_json()['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['status'] == 'Needs review'


def test_update_stage_progress_rejects_an_unknown_status(client, auth_headers, candidate, meeting_stage):
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Ghosted'},
    )
    assert resp.status_code == 400


def test_setting_status_to_no_cascades_to_candidate_stage(app, client, auth_headers, candidate, meeting_stage):
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'No'},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['stage'] == 'Rejected'
    stage = next(s for s in body['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['status'] == 'No'

    with app.app_context():
        c = Candidate.query.get(candidate.id)
        assert c.stage == 'Rejected'
        assert c.disqualified_at is not None


def test_rejecting_again_does_not_push_back_disqualified_at(app, client, auth_headers, candidate, meeting_stage):
    client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'No'},
    )
    with app.app_context():
        first_disqualified_at = Candidate.query.get(candidate.id).disqualified_at

    client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'No', 'notes': 'still rejected'},
    )
    with app.app_context():
        assert Candidate.query.get(candidate.id).disqualified_at == first_disqualified_at


def test_rejecting_leaves_other_stage_fields_intact(client, auth_headers, candidate, meeting_stage):
    client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'notes': 'Great candidate, just not a fit for this role'},
    )
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'No'},
    )
    stage = next(s for s in resp.get_json()['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['notes'] == 'Great candidate, just not a fit for this role'


def test_setting_status_to_yes_gates_onboarding_visible(app, client, auth_headers, candidate, meeting_stage):
    """Sanity check that 'Yes' (bare, no sub-state) is accepted and does
    NOT cascade like 'No' does - see routes/status.py's YES_STATUSES for
    the actual onboarding-visibility gating this feeds into."""
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Yes'},
    )
    assert resp.status_code == 200
    with app.app_context():
        c = Candidate.query.get(candidate.id)
        assert c.stage == 'Interview'  # unchanged - only 'No' cascades
        assert c.disqualified_at is None


def test_manual_scheduled_at_notifies_the_stages_interviewer(app, client, auth_headers, candidate, meeting_stage, user, monkeypatch):
    """The plain manual reschedule modal (stages without live-calendar
    scheduling still go through this, not book_stage_slot) - if the stage
    happens to have an interviewer assigned anyway, they should still hear
    about it."""
    calls = []
    monkeypatch.setattr(apply_module, 'send_interviewer_scheduled_email', lambda **kwargs: calls.append(kwargs) or True)
    with app.app_context():
        stage = MeetingStageTemplate.query.get(meeting_stage.id)
        stage.interviewer_user_id = user.id
        db.session.commit()

    when = (datetime.utcnow() + timedelta(days=3)).isoformat()
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'scheduled_at': when},
    )

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]['to_email'] == user.email


def test_manual_scheduled_at_sends_nothing_when_no_interviewer_assigned(client, auth_headers, candidate, meeting_stage, monkeypatch):
    calls = []
    monkeypatch.setattr(apply_module, 'send_interviewer_scheduled_email', lambda **kwargs: calls.append(kwargs) or True)

    when = (datetime.utcnow() + timedelta(days=3)).isoformat()
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'scheduled_at': when},
    )

    assert resp.status_code == 200
    assert calls == []


def test_rescheduling_clears_previously_sent_reminders(app, client, auth_headers, candidate, meeting_stage, user, monkeypatch):
    monkeypatch.setattr(apply_module, 'send_interviewer_scheduled_email', lambda **kwargs: True)
    with app.app_context():
        stage = MeetingStageTemplate.query.get(meeting_stage.id)
        stage.interviewer_user_id = user.id
        progress = CandidateStageProgress(
            candidate_id=candidate.id, meeting_stage_template_id=meeting_stage.id,
            reminder_1day_sent_at=datetime.utcnow(), reminder_4hr_sent_at=datetime.utcnow(),
        )
        db.session.add(progress)
        db.session.commit()

    when = (datetime.utcnow() + timedelta(days=5)).isoformat()
    client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'scheduled_at': when},
    )

    with app.app_context():
        progress = CandidateStageProgress.query.filter_by(
            candidate_id=candidate.id, meeting_stage_template_id=meeting_stage.id,
        ).first()
        assert progress.reminder_1day_sent_at is None
        assert progress.reminder_4hr_sent_at is None

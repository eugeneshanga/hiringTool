"""PUT /api/candidates/<id>/stages/<template_id> - the recruiter-facing
status/notes/scorecard update, and specifically the 'Rejected' status'
cascade onto Candidate.stage/disqualified_at (mirrors the auto-
disqualification path in routes/apply.py - see scheduled_jobs.py, which
picks up disqualified_at regardless of which path set it)."""
import pytest

from models import Candidate, CandidateStageProgress, db


@pytest.fixture
def candidate(app, job):
    with app.app_context():
        c = Candidate(name='Jane Applicant', email='jane@example.com', job_id=job.id, stage='Interview')
        db.session.add(c)
        db.session.commit()
        db.session.refresh(c)
        return c


def test_update_stage_progress_requires_auth(client, candidate, meeting_stage):
    resp = client.put(f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', json={'status': 'Completed'})
    assert resp.status_code == 401


def test_update_stage_progress_sets_status(client, auth_headers, candidate, meeting_stage):
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Completed'},
    )
    assert resp.status_code == 200
    stage = next(s for s in resp.get_json()['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['status'] == 'Completed'


def test_update_stage_progress_rejects_an_unknown_status(client, auth_headers, candidate, meeting_stage):
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Ghosted'},
    )
    assert resp.status_code == 400


def test_setting_status_to_rejected_cascades_to_candidate_stage(app, client, auth_headers, candidate, meeting_stage):
    resp = client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Rejected'},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['stage'] == 'Rejected'
    stage = next(s for s in body['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['status'] == 'Rejected'

    with app.app_context():
        c = Candidate.query.get(candidate.id)
        assert c.stage == 'Rejected'
        assert c.disqualified_at is not None


def test_rejecting_again_does_not_push_back_disqualified_at(app, client, auth_headers, candidate, meeting_stage):
    client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Rejected'},
    )
    with app.app_context():
        first_disqualified_at = Candidate.query.get(candidate.id).disqualified_at

    client.put(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}', headers=auth_headers,
        json={'status': 'Rejected', 'notes': 'still rejected'},
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
        json={'status': 'Rejected'},
    )
    stage = next(s for s in resp.get_json()['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['notes'] == 'Great candidate, just not a fit for this role'

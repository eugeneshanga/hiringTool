"""Candidate.stage vs. status: "stage" is the meeting stage the candidate is
currently on (the furthest one they've reached), "status" is that stage's
outcome (Yes/No/Maybe/...). Covers _current_stage_summary() and the
GET /api/candidates ?stage= / ?status= filters that read from it."""
import pytest

from models import Candidate, MeetingStageTemplate, db


@pytest.fixture
def two_stage_job(app, job, meeting_stage):
    """job already has meeting_stage ('CHHA Interview', sort_order 0); add an
    orientation stage after it."""
    with app.app_context():
        orientation = MeetingStageTemplate(
            job_id=job.id, meeting_type='In-person orientation',
            stage_name='CHHA Orientation', duration_minutes=60, sort_order=1,
        )
        db.session.add(orientation)
        db.session.commit()
        db.session.refresh(orientation)
        return {'job_id': job.id, 'interview_id': meeting_stage.id, 'orientation_id': orientation.id}


def _current(client, auth_headers, candidate_id):
    body = client.get(f'/api/candidates/{candidate_id}', headers=auth_headers).get_json()
    return body['current_stage']


def test_fresh_candidate_sits_on_the_first_meeting_stage(client, auth_headers, two_stage_job, candidate_factory):
    c = candidate_factory(job_id=two_stage_job['job_id'])
    summary = _current(client, auth_headers, c.id)
    assert summary['stage_name'] == 'CHHA Interview'
    assert summary['status'] == 'Upcoming'
    assert summary['scheduled_at'] is None


def test_current_stage_advances_to_the_furthest_reached_stage(client, auth_headers, two_stage_job, candidate_factory):
    c = candidate_factory(job_id=two_stage_job['job_id'])
    # Interview happened and got a Yes...
    client.put(
        f"/api/candidates/{c.id}/stages/{two_stage_job['interview_id']}",
        headers=auth_headers, json={'status': 'Yes'},
    )
    # ...then the recruiter scheduled orientation.
    client.put(
        f"/api/candidates/{c.id}/stages/{two_stage_job['orientation_id']}",
        headers=auth_headers, json={'scheduled_at': '2099-01-02T15:00:00'},
    )
    summary = _current(client, auth_headers, c.id)
    assert summary['stage_name'] == 'CHHA Orientation'
    assert summary['scheduled_at'] is not None


def test_current_stage_ignores_an_undecided_unscheduled_row(client, auth_headers, two_stage_job, candidate_factory):
    c = candidate_factory(job_id=two_stage_job['job_id'])
    # A bare progress row on the later stage with no decision and no
    # schedule doesn't count as "reached".
    client.put(
        f"/api/candidates/{c.id}/stages/{two_stage_job['orientation_id']}",
        headers=auth_headers, json={'notes': 'placeholder'},
    )
    assert _current(client, auth_headers, c.id)['stage_name'] == 'CHHA Interview'


def test_jobless_candidate_has_no_current_stage(client, auth_headers, candidate_factory):
    c = candidate_factory(job_id=None)
    assert _current(client, auth_headers, c.id) is None


def test_candidates_list_filters_by_meeting_stage_name(client, auth_headers, two_stage_job, candidate_factory):
    on_interview = candidate_factory(email='interview@example.com', job_id=two_stage_job['job_id'])
    on_orientation = candidate_factory(email='orientation@example.com', job_id=two_stage_job['job_id'])
    client.put(
        f"/api/candidates/{on_orientation.id}/stages/{two_stage_job['orientation_id']}",
        headers=auth_headers, json={'status': 'Yes'},
    )

    listed = client.get('/api/candidates?stage=CHHA Orientation', headers=auth_headers).get_json()
    ids = {c['id'] for c in listed}
    assert on_orientation.id in ids
    assert on_interview.id not in ids


def test_candidates_list_filters_by_status(client, auth_headers, two_stage_job, candidate_factory):
    yes = candidate_factory(email='yes@example.com', job_id=two_stage_job['job_id'])
    maybe = candidate_factory(email='maybe@example.com', job_id=two_stage_job['job_id'])
    client.put(
        f"/api/candidates/{yes.id}/stages/{two_stage_job['interview_id']}",
        headers=auth_headers, json={'status': 'Yes'},
    )
    client.put(
        f"/api/candidates/{maybe.id}/stages/{two_stage_job['interview_id']}",
        headers=auth_headers, json={'status': 'Maybe'},
    )

    listed = client.get('/api/candidates?status=Maybe', headers=auth_headers).get_json()
    ids = {c['id'] for c in listed}
    assert maybe.id in ids
    assert yes.id not in ids


def test_rejected_candidate_reads_as_no_on_the_first_stage(client, auth_headers, two_stage_job, candidate_factory):
    c = candidate_factory(job_id=two_stage_job['job_id'], stage='Rejected')
    # No progress rows at all (auto-disqualification path) - still surfaces
    # as 'No', matching the per-stage synthesized fallback.
    assert _current(client, auth_headers, c.id)['status'] == 'No'

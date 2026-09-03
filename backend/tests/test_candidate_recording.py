"""Upload/download/delete of a candidate's interview recording (see
CandidateStageProgress.recording_stored_filename, routes/candidates.py) -
recruiter-authenticated only, one recording per (candidate, meeting stage)."""
import io

import pytest

from models import Candidate, CandidateStageProgress, db


@pytest.fixture
def candidate(app, job):
    with app.app_context():
        c = Candidate(name='Jane Applicant', email='jane@example.com', job_id=job.id)
        db.session.add(c)
        db.session.commit()
        db.session.refresh(c)
        return c


def _video_file(name='recording.mp4'):
    return (io.BytesIO(b'fake video bytes'), name)


def test_upload_recording_requires_auth(client, candidate, meeting_stage):
    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording',
        data={'file': _video_file()},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 401


def test_upload_recording_requires_a_file(client, auth_headers, candidate, meeting_stage):
    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
    )
    assert resp.status_code == 400


def test_upload_recording_rejects_a_stage_from_a_different_job(app, client, auth_headers, candidate):
    with app.app_context():
        from models import Job, MeetingStageTemplate
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

    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{other_stage_id}/recording', headers=auth_headers,
        data={'file': _video_file()}, content_type='multipart/form-data',
    )
    assert resp.status_code == 400


def test_upload_recording_rejects_disallowed_extension(client, auth_headers, candidate, meeting_stage):
    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
        data={'file': _video_file('recording.exe')}, content_type='multipart/form-data',
    )
    assert resp.status_code == 400


def test_upload_recording_rejects_oversized_file(client, auth_headers, candidate, meeting_stage, monkeypatch):
    import routes.candidates as candidates_module
    monkeypatch.setattr(candidates_module, 'MAX_RECORDING_SIZE_BYTES', 10)

    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
        data={'file': _video_file()}, content_type='multipart/form-data',
    )
    assert resp.status_code == 400
    assert 'too large' in resp.get_json()['error']


def test_upload_then_download_recording_round_trips(app, client, auth_headers, candidate, meeting_stage):
    upload_resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
        data={'file': _video_file()}, content_type='multipart/form-data',
    )
    assert upload_resp.status_code == 200
    stage = next(s for s in upload_resp.get_json()['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['has_recording'] is True
    assert stage['recording_filename'] == 'recording.mp4'

    download_resp = client.get(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
    )
    assert download_resp.status_code == 200
    assert download_resp.data == b'fake video bytes'

    with app.app_context():
        progress = CandidateStageProgress.query.filter_by(
            candidate_id=candidate.id, meeting_stage_template_id=meeting_stage.id,
        ).first()
        assert progress is not None
        assert progress.recording_stored_filename is not None


def test_reupload_replaces_the_existing_recording(client, auth_headers, candidate, meeting_stage):
    client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
        data={'file': _video_file('first.mp4')}, content_type='multipart/form-data',
    )
    resp = client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
        data={'file': _video_file('second.mov')}, content_type='multipart/form-data',
    )
    assert resp.status_code == 200
    stage = next(s for s in resp.get_json()['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['recording_filename'] == 'second.mov'


def test_download_recording_404_when_none_uploaded(client, auth_headers, candidate, meeting_stage):
    resp = client.get(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
    )
    assert resp.status_code == 404


def test_delete_recording_removes_it(client, auth_headers, candidate, meeting_stage):
    client.post(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
        data={'file': _video_file()}, content_type='multipart/form-data',
    )
    delete_resp = client.delete(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
    )
    assert delete_resp.status_code == 200
    stage = next(s for s in delete_resp.get_json()['stages'] if s['meeting_stage_template_id'] == meeting_stage.id)
    assert stage['has_recording'] is False

    assert client.get(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
    ).status_code == 404


def test_delete_recording_404_when_none_uploaded(client, auth_headers, candidate, meeting_stage):
    resp = client.delete(
        f'/api/candidates/{candidate.id}/stages/{meeting_stage.id}/recording', headers=auth_headers,
    )
    assert resp.status_code == 404

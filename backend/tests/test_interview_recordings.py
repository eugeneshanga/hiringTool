"""scheduled_jobs.fetch_due_interview_recordings - pulling a RingCentral
recording back automatically once an interview that used a real per-
interview meeting (Interview.ringcentral_meeting_id) has happened, and
attaching it to the candidate's stage progress the same way a manual
upload would (routes/candidates.py's upload_recording writes the same two
columns)."""
import os
from datetime import datetime, timedelta

import pytest

import scheduled_jobs
from models import CandidateStageProgress, Interview, MeetingStageTemplate, db


@pytest.fixture
def stage_with_interviewer(app, job, meeting_stage, user):
    with app.app_context():
        stage = MeetingStageTemplate.query.get(meeting_stage.id)
        stage.interviewer_user_id = user.id
        db.session.commit()
        db.session.refresh(stage)
        return stage


def _interview_with_meeting(app, stage, candidate, scheduled_end, ringcentral_meeting_id='rc-meeting-1'):
    with app.app_context():
        interview = Interview(
            job_id=stage.job_id, meeting_stage_template_id=stage.id, stage_name=stage.stage_name,
            meeting_type='Interview', scheduled_start=scheduled_end - timedelta(minutes=20),
            scheduled_end=scheduled_end, ringcentral_meeting_id=ringcentral_meeting_id,
        )
        interview.candidates.append(candidate)
        db.session.add(interview)
        db.session.add(CandidateStageProgress(
            candidate_id=candidate.id, meeting_stage_template_id=stage.id,
            status='Upcoming', scheduled_at=interview.scheduled_start,
        ))
        db.session.commit()
        return interview.id


def test_fetches_and_attaches_a_recording_once_available(app, candidate_factory, stage_with_interviewer, monkeypatch):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    candidate_id = candidate.id
    scheduled_end = datetime.utcnow() - timedelta(hours=1)  # 1hr ago - inside the eligible window
    _interview_with_meeting(app, stage_with_interviewer, candidate, scheduled_end)

    monkeypatch.setattr(
        scheduled_jobs, 'get_meeting_recording_url',
        lambda interviewer, meeting_id: 'https://media.ringcentral.com/rcvideo/v1/recordings/abc',
    )
    monkeypatch.setattr(scheduled_jobs, 'download_recording', lambda interviewer, url: b'fake-video-bytes')

    scheduled_jobs.fetch_due_interview_recordings(app)

    with app.app_context():
        progress = CandidateStageProgress.query.filter_by(candidate_id=candidate_id).first()
        assert progress.recording_stored_filename is not None
        assert progress.recording_original_filename is not None
        path = os.path.join(app.config['UPLOAD_FOLDER'], 'candidates', str(candidate_id), progress.recording_stored_filename)
        with open(path, 'rb') as f:
            assert f.read() == b'fake-video-bytes'


def test_does_not_check_before_the_minimum_delay(app, candidate_factory, stage_with_interviewer, monkeypatch):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    candidate_id = candidate.id
    scheduled_end = datetime.utcnow() - timedelta(minutes=5)  # too recent - RC hasn't had time to process
    _interview_with_meeting(app, stage_with_interviewer, candidate, scheduled_end)

    calls = []
    monkeypatch.setattr(scheduled_jobs, 'get_meeting_recording_url', lambda i, m: calls.append(1) or None)

    scheduled_jobs.fetch_due_interview_recordings(app)
    assert calls == []


def test_gives_up_checking_after_the_max_age(app, candidate_factory, stage_with_interviewer, monkeypatch):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    candidate_id = candidate.id
    scheduled_end = datetime.utcnow() - timedelta(days=30)  # long past RECORDING_CHECK_MAX_AGE_DAYS
    _interview_with_meeting(app, stage_with_interviewer, candidate, scheduled_end)

    calls = []
    monkeypatch.setattr(scheduled_jobs, 'get_meeting_recording_url', lambda i, m: calls.append(1) or None)

    scheduled_jobs.fetch_due_interview_recordings(app)
    assert calls == []


def test_skips_a_candidate_who_already_has_a_recording(app, candidate_factory, stage_with_interviewer, monkeypatch):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    candidate_id = candidate.id
    scheduled_end = datetime.utcnow() - timedelta(hours=1)
    _interview_with_meeting(app, stage_with_interviewer, candidate, scheduled_end)
    with app.app_context():
        progress = CandidateStageProgress.query.filter_by(candidate_id=candidate_id).first()
        progress.recording_stored_filename = 'already_here.mp4'
        progress.recording_original_filename = 'already_here.mp4'
        db.session.commit()

    calls = []
    monkeypatch.setattr(scheduled_jobs, 'get_meeting_recording_url', lambda i, m: calls.append(1) or None)

    scheduled_jobs.fetch_due_interview_recordings(app)
    assert calls == []  # never even checked - nothing to do


def test_leaves_recording_unset_when_none_available_yet(app, candidate_factory, stage_with_interviewer, monkeypatch):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    candidate_id = candidate.id
    scheduled_end = datetime.utcnow() - timedelta(hours=1)
    _interview_with_meeting(app, stage_with_interviewer, candidate, scheduled_end)

    monkeypatch.setattr(scheduled_jobs, 'get_meeting_recording_url', lambda i, m: None)

    scheduled_jobs.fetch_due_interview_recordings(app)

    with app.app_context():
        progress = CandidateStageProgress.query.filter_by(candidate_id=candidate_id).first()
        assert progress.recording_stored_filename is None


def test_skips_interviews_with_no_ringcentral_meeting(app, candidate_factory, stage_with_interviewer, monkeypatch):
    """A booking that fell back to the static personal link - nothing to
    check at all, ringcentral_meeting_id is null."""
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    candidate_id = candidate.id
    scheduled_end = datetime.utcnow() - timedelta(hours=1)
    _interview_with_meeting(app, stage_with_interviewer, candidate, scheduled_end, ringcentral_meeting_id=None)

    calls = []
    monkeypatch.setattr(scheduled_jobs, 'get_meeting_recording_url', lambda i, m: calls.append(1) or None)

    scheduled_jobs.fetch_due_interview_recordings(app)
    assert calls == []

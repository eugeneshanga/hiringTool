"""scheduled_jobs.send_due_interview_reminders - the three lead-time (1 day
/ 4 hours / 1 hour) reminder emails to a stage's assigned interviewer before
a candidate's scheduled meeting. See CandidateStageProgress.reset_reminders
(models.py) for the reschedule-clears-them-back-to-null half of this."""
from datetime import datetime, timedelta

import pytest

import scheduled_jobs
from models import Candidate, CandidateStageProgress, MeetingStageTemplate, User, db


@pytest.fixture
def stage_with_interviewer(app, job, meeting_stage, user):
    with app.app_context():
        stage = MeetingStageTemplate.query.get(meeting_stage.id)
        stage.interviewer_user_id = user.id
        db.session.commit()
        db.session.refresh(stage)
        return stage


@pytest.fixture
def mock_reminder_email(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduled_jobs, 'send_interviewer_reminder_email', lambda **kwargs: calls.append(kwargs) or True
    )
    return calls


def _progress(app, candidate_id, template_id, scheduled_at, **overrides):
    with app.app_context():
        p = CandidateStageProgress(
            candidate_id=candidate_id, meeting_stage_template_id=template_id,
            status='Upcoming', scheduled_at=scheduled_at, **overrides,
        )
        db.session.add(p)
        db.session.commit()
        return p.id


def test_sends_all_due_tiers_when_booked_with_very_short_notice(
    app, candidate_factory, stage_with_interviewer, user, mock_reminder_email,
):
    """30 minutes out is inside all three windows at once (a candidate who
    booked with very short notice) - each tier is independently due and
    hasn't been sent yet, so all three fire in this one pass rather than
    silently dropping the more distant ones."""
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    scheduled_at = datetime.utcnow() + timedelta(minutes=30)
    _progress(app, candidate.id, stage_with_interviewer.id, scheduled_at)

    scheduled_jobs.send_due_interview_reminders(app)

    assert len(mock_reminder_email) == 3
    assert {c['to_email'] for c in mock_reminder_email} == {user.email}
    assert {c['lead_time_label'] for c in mock_reminder_email} == {'1 day', '4 hours', '1 hour'}

    with app.app_context():
        progress = CandidateStageProgress.query.filter_by(candidate_id=candidate.id).first()
        assert progress.reminder_1hr_sent_at is not None
        assert progress.reminder_4hr_sent_at is not None
        assert progress.reminder_1day_sent_at is not None


def test_does_not_resend_a_tier_already_marked_sent(
    app, candidate_factory, stage_with_interviewer, mock_reminder_email,
):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    scheduled_at = datetime.utcnow() + timedelta(minutes=30)
    _progress(
        app, candidate.id, stage_with_interviewer.id, scheduled_at,
        reminder_1hr_sent_at=datetime.utcnow(), reminder_4hr_sent_at=datetime.utcnow(),
        reminder_1day_sent_at=datetime.utcnow(),
    )

    scheduled_jobs.send_due_interview_reminders(app)

    assert mock_reminder_email == []


def test_does_not_send_for_a_stage_far_in_the_future(
    app, candidate_factory, stage_with_interviewer, mock_reminder_email,
):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    scheduled_at = datetime.utcnow() + timedelta(days=10)
    _progress(app, candidate.id, stage_with_interviewer.id, scheduled_at)

    scheduled_jobs.send_due_interview_reminders(app)

    assert mock_reminder_email == []


def test_does_not_send_for_a_stage_already_in_the_past(
    app, candidate_factory, stage_with_interviewer, mock_reminder_email,
):
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    scheduled_at = datetime.utcnow() - timedelta(minutes=5)
    _progress(app, candidate.id, stage_with_interviewer.id, scheduled_at)

    scheduled_jobs.send_due_interview_reminders(app)

    assert mock_reminder_email == []


def test_does_not_send_when_stage_has_no_interviewer_assigned(
    app, candidate_factory, job, meeting_stage, mock_reminder_email,
):
    candidate = candidate_factory(job_id=job.id)
    scheduled_at = datetime.utcnow() + timedelta(minutes=30)
    _progress(app, candidate.id, meeting_stage.id, scheduled_at)  # meeting_stage has no interviewer here

    scheduled_jobs.send_due_interview_reminders(app)

    assert mock_reminder_email == []


def test_only_the_due_tiers_fire_at_the_4_hour_mark(
    app, candidate_factory, stage_with_interviewer, user, mock_reminder_email,
):
    """4.5 hours out: within the 1-day window, at the 4-hour window's edge
    (not yet <= 4 hours), and well outside the 1-hour window - only the
    1-day tier should be due."""
    candidate = candidate_factory(job_id=stage_with_interviewer.job_id)
    scheduled_at = datetime.utcnow() + timedelta(hours=4, minutes=30)
    _progress(app, candidate.id, stage_with_interviewer.id, scheduled_at)

    scheduled_jobs.send_due_interview_reminders(app)

    assert len(mock_reminder_email) == 1
    assert mock_reminder_email[0]['lead_time_label'] == '1 day'
    with app.app_context():
        progress = CandidateStageProgress.query.filter_by(candidate_id=candidate.id).first()
        assert progress.reminder_1day_sent_at is not None
        assert progress.reminder_4hr_sent_at is None
        assert progress.reminder_1hr_sent_at is None

"""scheduled_jobs.send_due_rejection_emails - the delayed rejection email
for a candidate auto-disqualified by their screening answers (see
routes/apply.py's apply()). Tests call the function directly rather than
going through the actual BackgroundScheduler/APScheduler thread - that
thread is just a timer calling this same function, and start_scheduler()
itself is guarded to never run during tests (see conftest.py's
SCHEDULER_ENABLED override and app.py's WERKZEUG_RUN_MAIN guard).
"""
from datetime import datetime, timedelta

import pytest

import scheduled_jobs
from models import Candidate, db


@pytest.fixture(autouse=True)
def mock_rejection_email(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduled_jobs, 'send_rejection_email', lambda **kwargs: calls.append(kwargs) or True)
    return calls


def _disqualified_candidate(app, job, *, disqualified_minutes_ago, rejection_email_sent=False):
    with app.app_context():
        candidate = Candidate(
            name='Jane Applicant', email='jane@example.com', job_id=job.id,
            stage='Rejected',
            disqualified_at=datetime.utcnow() - timedelta(minutes=disqualified_minutes_ago),
            rejection_email_sent_at=datetime.utcnow() if rejection_email_sent else None,
        )
        db.session.add(candidate)
        db.session.commit()
        return candidate.id


def test_sends_rejection_email_once_the_delay_has_elapsed(app, job, mock_rejection_email):
    app.config['REJECTION_EMAIL_DELAY_MINUTES'] = 60
    candidate_id = _disqualified_candidate(app, job, disqualified_minutes_ago=61)

    scheduled_jobs.send_due_rejection_emails(app)

    assert len(mock_rejection_email) == 1
    assert mock_rejection_email[0]['to_email'] == 'jane@example.com'
    assert mock_rejection_email[0]['job_title'] == job.title
    with app.app_context():
        candidate = Candidate.query.get(candidate_id)
        assert candidate.rejection_email_sent_at is not None


def test_does_not_send_before_the_delay_has_elapsed(app, job, mock_rejection_email):
    app.config['REJECTION_EMAIL_DELAY_MINUTES'] = 60
    _disqualified_candidate(app, job, disqualified_minutes_ago=10)

    scheduled_jobs.send_due_rejection_emails(app)

    assert mock_rejection_email == []


def test_does_not_resend_once_already_sent(app, job, mock_rejection_email):
    app.config['REJECTION_EMAIL_DELAY_MINUTES'] = 60
    _disqualified_candidate(app, job, disqualified_minutes_ago=120, rejection_email_sent=True)

    scheduled_jobs.send_due_rejection_emails(app)

    assert mock_rejection_email == []


def test_ignores_candidates_who_were_never_disqualified(app, job, mock_rejection_email):
    with app.app_context():
        db.session.add(Candidate(name='Qualified Candidate', email='qualified@example.com', job_id=job.id))
        db.session.commit()

    scheduled_jobs.send_due_rejection_emails(app)

    assert mock_rejection_email == []


def test_a_failed_send_does_not_block_the_rest_and_is_retried_next_time(app, job, monkeypatch):
    app.config['REJECTION_EMAIL_DELAY_MINUTES'] = 60
    _disqualified_candidate(app, job, disqualified_minutes_ago=90)
    with app.app_context():
        other = Candidate(
            name='Other Candidate', email='other@example.com', job_id=job.id, stage='Rejected',
            disqualified_at=datetime.utcnow() - timedelta(minutes=90),
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.id

    calls = []

    def _flaky_send(**kwargs):
        if kwargs['to_email'] == 'jane@example.com':
            raise RuntimeError('provider is down')
        calls.append(kwargs)
        return True

    monkeypatch.setattr(scheduled_jobs, 'send_rejection_email', _flaky_send)

    scheduled_jobs.send_due_rejection_emails(app)

    # The failing one is left unsent (so a future run retries it); the
    # other one still went out despite that failure.
    assert len(calls) == 1
    with app.app_context():
        jane = Candidate.query.filter_by(email='jane@example.com').first()
        assert jane.rejection_email_sent_at is None
        assert Candidate.query.get(other_id).rejection_email_sent_at is not None

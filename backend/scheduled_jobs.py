"""Background scheduling for delayed application-related email - the
rejection email (sent some delay after a candidate is auto-disqualified by
their screening answers - see routes/apply.py's apply(), and
Candidate.disqualified_at's docstring in models.py), and interviewer
reminder emails at three lead times before a scheduled meeting stage.

Runs in-process via APScheduler, not a real task queue - same caveat as
extensions.py's rate limiter and email_sender.py's send cap: fine for a
single process (dev, or one production worker), but a multi-worker
deployment would need a real queue (Celery+Redis or similar) instead, since
each worker would otherwise run its own independent scheduler and duplicate
sends.
"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from email_sender import send_interviewer_reminder_email, send_rejection_email
from models import Candidate, CandidateStageProgress, MeetingStageTemplate, User, db

# How often the scheduler checks for rejections/reminders that have become
# due - doesn't need to be frequent since the shortest lead time (1 hour) is
# still much longer than this; it just bounds how late a send can run past
# its due time.
CHECK_INTERVAL_MINUTES = 5

# (lead time before the scheduled stage, the CandidateStageProgress column
# marking that tier sent, what the email calls it) - see
# send_due_interview_reminders below and CandidateStageProgress.
# reset_reminders (models.py) for how a reschedule clears these so they
# re-fire against the new time.
_REMINDER_TIERS = (
    (timedelta(days=1), 'reminder_1day_sent_at', '1 day'),
    (timedelta(hours=4), 'reminder_4hr_sent_at', '4 hours'),
    (timedelta(hours=1), 'reminder_1hr_sent_at', '1 hour'),
)


def send_due_rejection_emails(app):
    """Finds every disqualified candidate whose delay has elapsed and no
    rejection email has gone out yet, and sends it. Takes the app explicitly
    (rather than relying on an ambient current_app) since this runs from a
    background thread, outside any request - needs its own app context."""
    with app.app_context():
        delay = timedelta(minutes=app.config['REJECTION_EMAIL_DELAY_MINUTES'])
        due = Candidate.query.filter(
            Candidate.disqualified_at.isnot(None),
            Candidate.rejection_email_sent_at.is_(None),
            Candidate.disqualified_at <= datetime.utcnow() - delay,
        ).all()
        for candidate in due:
            try:
                send_rejection_email(
                    to_email=candidate.email,
                    candidate_name=candidate.name,
                    job_title=candidate.job.title if candidate.job else 'this position',
                )
            except Exception:
                app.logger.exception("Failed to send rejection email for candidate %s", candidate.id)
                continue
            candidate.rejection_email_sent_at = datetime.utcnow()
            db.session.commit()


def send_due_interview_reminders(app):
    """For each of the three lead times in _REMINDER_TIERS, finds every
    scheduled-but-not-yet-past meeting stage that's crossed into that tier's
    window and hasn't had that tier's reminder sent yet, and emails the
    stage's assigned interviewer once. Only ever sent when the stage has an
    interviewer assigned (MeetingStageTemplate.interviewer_user_id) - a
    stage without one just never matches. Runs the three tiers independently
    in one pass rather than needing three separate scheduled jobs."""
    with app.app_context():
        now = datetime.utcnow()
        for lead_time, sent_at_column, label in _REMINDER_TIERS:
            due = (
                CandidateStageProgress.query
                .join(MeetingStageTemplate)
                .filter(
                    MeetingStageTemplate.interviewer_user_id.isnot(None),
                    CandidateStageProgress.scheduled_at.isnot(None),
                    # Still in the future (a stale/missed reminder for a
                    # stage that's already happened is just noise, not
                    # useful) and now within this tier's lead time of it.
                    CandidateStageProgress.scheduled_at > now,
                    CandidateStageProgress.scheduled_at <= now + lead_time,
                    getattr(CandidateStageProgress, sent_at_column).is_(None),
                )
                .all()
            )
            for progress in due:
                candidate = progress.candidate
                template = progress.meeting_stage_template
                interviewer = User.query.get(template.interviewer_user_id) if template else None
                if not candidate or not candidate.job or not interviewer:
                    continue
                try:
                    send_interviewer_reminder_email(
                        to_email=interviewer.email,
                        interviewer_name=interviewer.name,
                        candidate_name=candidate.name,
                        job_title=candidate.job.title,
                        stage_name=template.stage_name,
                        scheduled_start=progress.scheduled_at,
                        lead_time_label=label,
                    )
                except Exception:
                    app.logger.exception(
                        "Failed to send %s interview reminder for candidate %s", label, candidate.id,
                    )
                    continue
                setattr(progress, sent_at_column, datetime.utcnow())
                db.session.commit()


def start_scheduler(app):
    """Starts the background scheduler thread. Call once, from app.py's
    __main__ block only (see the comment there for why) - not from
    create_app() itself, since the Werkzeug reloader runs create_app() twice
    per launch (once in its outer monitor process, once in the real serving
    child) and starting a second scheduler in the monitor process would
    double every send."""
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(lambda: send_due_rejection_emails(app), 'interval', minutes=CHECK_INTERVAL_MINUTES)
    scheduler.add_job(lambda: send_due_interview_reminders(app), 'interval', minutes=CHECK_INTERVAL_MINUTES)
    scheduler.start()
    return scheduler

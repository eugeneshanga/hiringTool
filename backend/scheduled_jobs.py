"""Background scheduling for delayed application-related email - today just
the rejection email, sent some delay after a candidate is auto-disqualified
by their screening answers (see routes/apply.py's apply(), and
Candidate.disqualified_at's docstring in models.py).

Runs in-process via APScheduler, not a real task queue - same caveat as
extensions.py's rate limiter and email_sender.py's send cap: fine for a
single process (dev, or one production worker), but a multi-worker
deployment would need a real queue (Celery+Redis or similar) instead, since
each worker would otherwise run its own independent scheduler and duplicate
sends.
"""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from email_sender import send_rejection_email
from models import Candidate, db

# How often the scheduler checks for rejections that have become due -
# doesn't need to be frequent since the delay itself is on the order of an
# hour; this just bounds how late a send can run past its due time.
CHECK_INTERVAL_MINUTES = 5


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


def start_scheduler(app):
    """Starts the background scheduler thread. Call once, from app.py's
    __main__ block only (see the comment there for why) - not from
    create_app() itself, since the Werkzeug reloader runs create_app() twice
    per launch (once in its outer monitor process, once in the real serving
    child) and starting a second scheduler in the monitor process would
    double every send."""
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(lambda: send_due_rejection_emails(app), 'interval', minutes=CHECK_INTERVAL_MINUTES)
    scheduler.start()
    return scheduler

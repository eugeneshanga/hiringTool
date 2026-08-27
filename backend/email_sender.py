"""Provider-agnostic email sending for the public apply flow.

Two things live here:

1. The actual send mechanism - an EmailProvider interface. ConsoleEmailProvider
   is the local dev / test suite default (grab the apply link or confirmation
   code straight from the console/log output, no real mail infrastructure
   needed); PostmarkEmailProvider sends for real via Postmark's HTTP API once
   EMAIL_PROVIDER=postmark and POSTMARK_SERVER_TOKEN/EMAIL_FROM_ADDRESS are
   set (see config.py). Adding another provider later means writing one more
   EmailProvider and pointing get_provider() at it - nothing above this
   module changes.
2. A blunt, app-wide rolling-hour send cap shared by every email this module
   sends, independent of the per-IP / per-email-per-job limits on
   POST /api/apply itself (see routes/apply.py) - a last line of defense
   against a bug or an anti-abuse gap letting a burst of email through, not
   the primary defense.

Callers (routes/apply.py today) are expected to treat a failed send as
non-fatal to the request that triggered it - the underlying write (creating
the Candidate, booking the Interview) already succeeded, and a notification
failure shouldn't turn that into a 500 for the person who just applied.
"""
import threading
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime, timedelta

import requests
from flask import current_app

POSTMARK_SEND_URL = 'https://api.postmarkapp.com/email'
# Postmark itself times out slower than this on a bad day; failing fast here
# means a Postmark outage can't hang the request that triggered the email
# (see module docstring - a failed send must stay non-fatal to the caller).
POSTMARK_TIMEOUT_SECONDS = 10


class EmailProvider(ABC):
    """Minimal interface every concrete sender implements."""

    @abstractmethod
    def send(self, to_email, subject, text_body):
        """Send one email. Should raise on a real delivery failure rather
        than swallowing it - _send() below is what decides whether that's
        allowed to break the caller's request."""


class ConsoleEmailProvider(EmailProvider):
    """Default/dev provider - logs the email instead of sending it. Goes
    through current_app.logger (not a plain module-level logging.getLogger)
    specifically so it's actually visible in the dev server's console: a
    bare module logger has no level/handler of its own and inherits the
    interpreter's default root level (WARNING), which silently swallows
    .info() calls unless something has configured logging - current_app's
    logger is guaranteed to have a handler and (see app.py's create_app) is
    set to INFO, so this reliably shows up where a dev would look for it."""

    def send(self, to_email, subject, text_body):
        current_app.logger.info(
            "EMAIL to=%s subject=%r\n%s\n%s\n%s",
            to_email, subject, '-' * 60, text_body, '-' * 60,
        )


class PostmarkEmailProvider(EmailProvider):
    """Sends via Postmark's HTTP API (no SDK dependency - this is a single
    small POST, and `requests` is already a dependency for google_calendar.py).
    Chosen over relaying through a personal/Workspace Gmail account: Postmark
    is built for transactional mail specifically, manages IP reputation and
    SPF/DKIM/DMARC signing for you, and - the actual anti-abuse property this
    app wants - proactively monitors bounce/complaint rates and suspends an
    abusing account rather than letting it degrade a shared IP's reputation
    with the wider internet. The app's own defenses (honeypot, per-IP and
    per-email-per-job rate limits in routes/apply.py, the hourly cap below)
    are still the first line; this is the backstop.

    server_token/from_email are read once at construction (not per-send) so
    a misconfigured deployment fails at the first send attempt with a clear
    error rather than silently degrading."""

    def __init__(self, server_token, from_email):
        if not server_token:
            raise RuntimeError('POSTMARK_SERVER_TOKEN is not set (required when EMAIL_PROVIDER=postmark)')
        if not from_email:
            raise RuntimeError('EMAIL_FROM_ADDRESS is not set (required when EMAIL_PROVIDER=postmark)')
        self._server_token = server_token
        self._from_email = from_email

    def send(self, to_email, subject, text_body):
        response = requests.post(
            POSTMARK_SEND_URL,
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-Postmark-Server-Token': self._server_token,
            },
            json={
                'From': self._from_email,
                'To': to_email,
                'Subject': subject,
                'TextBody': text_body,
                # Keeps this app's automated mail out of Postmark's "broadcast"
                # stream accounting/limits, which is priced and rate-limited
                # separately from transactional - these are all one-to-one,
                # triggered-by-an-action emails, i.e. transactional.
                'MessageStream': 'outbound',
            },
            timeout=POSTMARK_TIMEOUT_SECONDS,
        )
        # Postmark's error body (ErrorCode/Message) is worth surfacing
        # whether it comes back with a 2xx (e.g. inactive recipient) or a
        # non-2xx (e.g. 422 for a rejected request, such as sending outside
        # an unapproved trial account's allowed recipients) - check for it
        # before raise_for_status() so that message isn't lost in favor of
        # a bare "422 Client Error" once raise_for_status() tears the body
        # down. Only fall back to raise_for_status()'s generic error if the
        # body isn't the JSON shape Postmark normally sends (e.g. a proxy
        # error page on an outage).
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if payload and payload.get('ErrorCode'):
            raise RuntimeError(f"Postmark error {payload['ErrorCode']}: {payload.get('Message')}")
        response.raise_for_status()


def get_provider():
    """Which EmailProvider to use - config-driven (EMAIL_PROVIDER) so
    switching to a real provider later is a config change, not a code
    change. 'console' (default) and 'postmark' exist today."""
    provider_name = current_app.config.get('EMAIL_PROVIDER', 'console')
    if provider_name == 'console':
        return ConsoleEmailProvider()
    if provider_name == 'postmark':
        return PostmarkEmailProvider(
            server_token=current_app.config.get('POSTMARK_SERVER_TOKEN'),
            from_email=current_app.config.get('EMAIL_FROM_ADDRESS'),
        )
    raise NotImplementedError(
        f"EMAIL_PROVIDER={provider_name!r} has no EmailProvider implementation - only 'console' and 'postmark' exist."
    )


# --- global send cap ---------------------------------------------------------

# App-wide, across every template this module sends - see module docstring.
GLOBAL_HOURLY_SEND_CAP = 100

_send_timestamps = deque()
_send_lock = threading.Lock()


def _reserve_send_slot():
    """True (and reserves a slot) if under the rolling-hour cap, else False.
    In-process only, like Flask-Limiter's default memory:// storage (see
    extensions.py) - a multi-worker deployment would need a shared store for
    this cap to hold app-wide rather than per-worker."""
    now = datetime.utcnow()
    window_start = now - timedelta(hours=1)
    with _send_lock:
        while _send_timestamps and _send_timestamps[0] < window_start:
            _send_timestamps.popleft()
        if len(_send_timestamps) >= GLOBAL_HOURLY_SEND_CAP:
            return False
        _send_timestamps.append(now)
        return True


def _send(to_email, subject, text_body):
    """True if the email was handed to the provider, False if it was
    skipped because the global cap was hit - logged either way, never raised
    for a cap hit (that's an expected, handled condition, not an error)."""
    if not _reserve_send_slot():
        current_app.logger.warning(
            "Global application-email send cap (%d/hour) hit - skipping email to %s (%r)",
            GLOBAL_HOURLY_SEND_CAP, to_email, subject,
        )
        return False
    get_provider().send(to_email, subject, text_body)
    return True


# --- templates ------------------------------------------------------------

def send_schedule_interview_email(to_email, candidate_name, job_title, apply_url, expires_at):
    """Email #1 (see routes/apply.py step 2): the link to that candidate's
    job-specific prescreen + scheduling page."""
    subject = f"Next steps for your {job_title} application"
    text_body = (
        f"Hi {candidate_name},\n\n"
        f"Thanks for applying to the {job_title} position. The next step is to "
        f"answer a few quick questions and pick a time for your interview:\n\n"
        f"{apply_url}\n\n"
        f"This link is valid until {expires_at.strftime('%B %d, %Y')}.\n\n"
        f"- The Hiring Team\n"
        f"(This is an automated message - please don't reply to this email.)\n"
    )
    return _send(to_email, subject, text_body)


def send_confirmation_email(
    to_email, candidate_name, job_title, stage_name, scheduled_start, meeting_link, confirmation_code, status_url,
):
    """Email #2 (see routes/apply.py step 6): sent right after a candidate
    books their slot. scheduled_start is naive UTC, per this app's storage
    convention (see models.iso_utc)."""
    subject = f"You're confirmed: {job_title} - {stage_name}"
    text_body = (
        f"Hi {candidate_name},\n\n"
        f"You're confirmed for your {stage_name} for the {job_title} position.\n\n"
        f"When: {scheduled_start.strftime('%A, %B %d, %Y at %I:%M %p')} UTC\n"
        f"Meeting link: {meeting_link}\n"
        f"Confirmation code: {confirmation_code}\n\n"
        f"You can check your status anytime here:\n{status_url}\n\n"
        f"- The Hiring Team\n"
        f"(This is an automated message - please don't reply to this email.)\n"
    )
    return _send(to_email, subject, text_body)


def send_rejection_email(to_email, candidate_name, job_title):
    """Sent by scheduled_jobs.send_due_rejection_emails, some delay after a
    candidate's screening answers were auto-evaluated as disqualifying (see
    routes/apply.py's apply()) - never sent inline with that request, so the
    delay is real rather than simulated by, say, a setTimeout on the
    frontend."""
    subject = f"Update on your {job_title} application"
    text_body = (
        f"Hi {candidate_name},\n\n"
        f"Thank you for your interest in the {job_title} position and for taking the time "
        f"to apply. After reviewing your application, we've decided not to move forward at "
        f"this time.\n\n"
        f"We appreciate your interest and wish you the best in your search.\n\n"
        f"- The Hiring Team\n"
        f"(This is an automated message - please don't reply to this email.)\n"
    )
    return _send(to_email, subject, text_body)

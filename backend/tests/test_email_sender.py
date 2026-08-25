"""email_sender.py: the console provider, provider selection, the global
send cap, and the two template functions. Nothing here talks to real mail
infrastructure - the console provider *is* the thing under test for
delivery, and template tests swap in a spy provider via monkeypatch.
"""
from datetime import datetime, timedelta

import pytest

import email_sender


class _SpyProvider:
    def __init__(self):
        self.sent = []

    def send(self, to_email, subject, text_body):
        self.sent.append((to_email, subject, text_body))


@pytest.fixture(autouse=True)
def clean_send_window():
    """The rolling-hour send cap is module-level, in-process state (see
    email_sender._send_timestamps) - reset it around every test so one
    test's sends can't count against another's cap."""
    email_sender._send_timestamps.clear()
    yield
    email_sender._send_timestamps.clear()


@pytest.fixture
def spy_provider(monkeypatch):
    spy = _SpyProvider()
    monkeypatch.setattr(email_sender, 'get_provider', lambda: spy)
    return spy


# --- provider selection -----------------------------------------------------

def test_get_provider_defaults_to_console(app):
    with app.app_context():
        assert isinstance(email_sender.get_provider(), email_sender.ConsoleEmailProvider)


def test_get_provider_rejects_unimplemented_provider(app):
    with app.app_context(), app.test_request_context():
        app.config['EMAIL_PROVIDER'] = 'sendgrid'
        with pytest.raises(NotImplementedError):
            email_sender.get_provider()


def test_console_provider_logs_the_email(app, caplog):
    # Goes through current_app.logger, not a bare module logger - see
    # ConsoleEmailProvider's docstring for why (a plain logging.getLogger
    # silently drops .info() by default, which would defeat the entire
    # point of this provider: making the link visible in the console).
    with app.app_context(), caplog.at_level('INFO', logger=app.logger.name):
        email_sender.ConsoleEmailProvider().send('jane@example.com', 'Subject line', 'Body text')

    assert 'jane@example.com' in caplog.text
    assert 'Subject line' in caplog.text
    assert 'Body text' in caplog.text


# --- global send cap ----------------------------------------------------------

def test_send_succeeds_under_the_cap(spy_provider):
    assert email_sender._send('a@example.com', 'Subject', 'Body') is True
    assert spy_provider.sent == [('a@example.com', 'Subject', 'Body')]


def test_send_is_skipped_once_the_cap_is_hit(app, spy_provider, monkeypatch):
    monkeypatch.setattr(email_sender, 'GLOBAL_HOURLY_SEND_CAP', 2)

    with app.app_context():  # the cap-hit path logs via current_app.logger
        assert email_sender._send('a@example.com', 'Subject', 'Body') is True
        assert email_sender._send('b@example.com', 'Subject', 'Body') is True
        assert email_sender._send('c@example.com', 'Subject', 'Body') is False

    assert len(spy_provider.sent) == 2  # the third never reached the provider


def test_cap_window_rolls_off_after_an_hour(spy_provider, monkeypatch):
    monkeypatch.setattr(email_sender, 'GLOBAL_HOURLY_SEND_CAP', 1)
    email_sender._send_timestamps.append(datetime.utcnow() - timedelta(hours=2))

    assert email_sender._send('a@example.com', 'Subject', 'Body') is True  # stale entry rolled off first


# --- templates ------------------------------------------------------------

def test_schedule_interview_email_content(spy_provider):
    expires_at = datetime.utcnow() + timedelta(days=14)

    result = email_sender.send_schedule_interview_email(
        to_email='jane@example.com', candidate_name='Jane Applicant', job_title='CHHA',
        apply_url='https://example.com/apply/schedule/abc123', expires_at=expires_at,
    )

    assert result is True
    to_email, subject, body = spy_provider.sent[0]
    assert to_email == 'jane@example.com'
    assert 'CHHA' in subject
    assert 'Jane Applicant' in body
    assert 'https://example.com/apply/schedule/abc123' in body
    assert expires_at.strftime('%B %d, %Y') in body


def test_confirmation_email_content(spy_provider):
    scheduled_start = datetime(2026, 9, 1, 15, 30)

    result = email_sender.send_confirmation_email(
        to_email='jane@example.com', candidate_name='Jane Applicant', job_title='CHHA',
        stage_name='Virtual interview', scheduled_start=scheduled_start,
        meeting_link='https://meet.google.com/abc-defg-hij', confirmation_code='7X4KMPQ2R',
        status_url='https://example.com/status?code=7X4KMPQ2R',
    )

    assert result is True
    to_email, subject, body = spy_provider.sent[0]
    assert to_email == 'jane@example.com'
    assert 'CHHA' in subject and 'Virtual interview' in subject
    assert 'https://meet.google.com/abc-defg-hij' in body
    assert '7X4KMPQ2R' in body
    assert 'https://example.com/status?code=7X4KMPQ2R' in body

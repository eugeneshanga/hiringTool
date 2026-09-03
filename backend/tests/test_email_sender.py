"""email_sender.py: is_plausible_email, the console/Postmark/Resend
providers, provider selection, the global send cap, and the three template
functions. Nothing here talks to real mail infrastructure - the console
provider *is* the thing under test for delivery, Postmark/Resend's HTTP
calls are faked via monkeypatch, and template tests swap in a spy provider
via monkeypatch.
"""
from datetime import datetime, timedelta

import pytest

import email_sender


class _SpyProvider:
    def __init__(self):
        self.sent = []

    def send(self, to_email, subject, text_body):
        self.sent.append((to_email, subject, text_body))


class _FakePostmarkResponse:
    """Stands in for requests.Response - only what PostmarkEmailProvider.send
    actually touches (raise_for_status/.json)."""

    def __init__(self, status_code=200, error_code=0, message='OK'):
        self.status_code = status_code
        self._payload = {'ErrorCode': error_code, 'Message': message}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise email_sender.requests.HTTPError(f'{self.status_code} error')

    def json(self):
        return self._payload


class _FakeResendResponse:
    """Stands in for requests.Response - only what ResendEmailProvider.send
    actually touches (raise_for_status/.json). Resend's success body has no
    'message' key at all (just an id) - only an error body does - so
    passing message=None (the default) produces a success-shaped body."""

    def __init__(self, status_code=200, message=None, name=None):
        self.status_code = status_code
        self._payload = {'id': 'fake-id'} if message is None else {'message': message, 'name': name}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise email_sender.requests.HTTPError(f'{self.status_code} error')

    def json(self):
        return self._payload


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


# --- is_plausible_email -------------------------------------------------------

@pytest.mark.parametrize('value', [
    'jane@example.com',
    'first.last+tag@sub.example.co.uk',
    'a@b.co',
])
def test_is_plausible_email_accepts_normal_addresses(value):
    assert email_sender.is_plausible_email(value) is True


@pytest.mark.parametrize('value', [
    None,
    '',
    'not-an-email',
    'missing-domain@',
    '@missing-local.com',
    'no-tld@localhost',
    'has space@example.com',
    'victim@x.com\r\nBcc: attacker@evil.com',  # the actual header-injection payload
    'victim@x.com\n',
    'tab\there@example.com',
])
def test_is_plausible_email_rejects_malformed_or_malicious_values(value):
    assert email_sender.is_plausible_email(value) is False


# --- provider selection -----------------------------------------------------

def test_get_provider_defaults_to_console(app):
    with app.app_context():
        assert isinstance(email_sender.get_provider(), email_sender.ConsoleEmailProvider)


def test_get_provider_rejects_unimplemented_provider(app):
    with app.app_context(), app.test_request_context():
        app.config['EMAIL_PROVIDER'] = 'sendgrid'
        with pytest.raises(NotImplementedError):
            email_sender.get_provider()


def test_get_provider_returns_postmark_when_configured(app):
    with app.app_context():
        app.config['EMAIL_PROVIDER'] = 'postmark'
        app.config['POSTMARK_SERVER_TOKEN'] = 'test-token'
        app.config['EMAIL_FROM_ADDRESS'] = 'noreply@example.com'
        provider = email_sender.get_provider()
        assert isinstance(provider, email_sender.PostmarkEmailProvider)


def test_postmark_provider_requires_server_token():
    with pytest.raises(RuntimeError):
        email_sender.PostmarkEmailProvider(server_token=None, from_email='noreply@example.com')


def test_postmark_provider_requires_from_email():
    with pytest.raises(RuntimeError):
        email_sender.PostmarkEmailProvider(server_token='test-token', from_email=None)


def test_get_provider_returns_resend_when_configured(app):
    with app.app_context():
        app.config['EMAIL_PROVIDER'] = 'resend'
        app.config['RESEND_API_KEY'] = 'test-key'
        app.config['EMAIL_FROM_ADDRESS'] = 'noreply@example.com'
        provider = email_sender.get_provider()
        assert isinstance(provider, email_sender.ResendEmailProvider)


def test_resend_provider_requires_api_key():
    with pytest.raises(RuntimeError):
        email_sender.ResendEmailProvider(api_key=None, from_email='noreply@example.com')


def test_resend_provider_requires_from_email():
    with pytest.raises(RuntimeError):
        email_sender.ResendEmailProvider(api_key='test-key', from_email=None)


# --- Postmark send -----------------------------------------------------------

def test_postmark_provider_sends_successfully(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return _FakePostmarkResponse(status_code=200, error_code=0)

    monkeypatch.setattr(email_sender.requests, 'post', fake_post)
    provider = email_sender.PostmarkEmailProvider(server_token='test-token', from_email='noreply@example.com')

    provider.send('jane@example.com', 'Subject line', 'Body text')

    assert len(calls) == 1
    url, headers, payload, timeout = calls[0]
    assert url == email_sender.POSTMARK_SEND_URL
    assert headers['X-Postmark-Server-Token'] == 'test-token'
    assert payload['From'] == 'noreply@example.com'
    assert payload['To'] == 'jane@example.com'
    assert payload['Subject'] == 'Subject line'
    assert payload['TextBody'] == 'Body text'
    assert payload['MessageStream'] == 'outbound'
    assert timeout == email_sender.POSTMARK_TIMEOUT_SECONDS


def test_postmark_provider_raises_generic_http_error_without_a_parseable_body(monkeypatch):
    # No usable Postmark JSON body (e.g. a proxy error page on an outage) -
    # falls back to requests' own error rather than a RuntimeError.
    monkeypatch.setattr(email_sender.requests, 'post', lambda url, **kw: _FakePostmarkResponse(status_code=500))
    provider = email_sender.PostmarkEmailProvider(server_token='test-token', from_email='noreply@example.com')

    with pytest.raises(email_sender.requests.HTTPError):
        provider.send('jane@example.com', 'Subject', 'Body')


def test_postmark_provider_surfaces_error_message_on_non_2xx_status(monkeypatch):
    # Postmark's own rejection reason (e.g. 422 for a trial account sending
    # outside its allowed recipients) must not get lost behind
    # raise_for_status()'s generic "422 Client Error" - regression coverage
    # for exactly that bug.
    monkeypatch.setattr(
        email_sender.requests, 'post',
        lambda url, **kw: _FakePostmarkResponse(
            status_code=422, error_code=412,
            message="all recipient addresses must share the same domain as the 'From' address",
        ),
    )
    provider = email_sender.PostmarkEmailProvider(server_token='test-token', from_email='noreply@example.com')

    with pytest.raises(RuntimeError, match='same domain'):
        provider.send('jane@example.com', 'Subject', 'Body')


def test_postmark_provider_raises_on_error_code_with_200_status(monkeypatch):
    # Postmark returns HTTP 200 with a non-zero ErrorCode for some failures
    # (e.g. an inactive/bounced recipient) rather than a non-2xx status.
    monkeypatch.setattr(
        email_sender.requests, 'post',
        lambda url, **kw: _FakePostmarkResponse(status_code=200, error_code=406, message='Inactive recipient'),
    )
    provider = email_sender.PostmarkEmailProvider(server_token='test-token', from_email='noreply@example.com')

    with pytest.raises(RuntimeError, match='406'):
        provider.send('jane@example.com', 'Subject', 'Body')


def test_postmark_provider_rejects_implausible_email(monkeypatch):
    # Should never even build the request - no requests.post call at all.
    calls = []
    monkeypatch.setattr(email_sender.requests, 'post', lambda *a, **kw: calls.append(1))
    provider = email_sender.PostmarkEmailProvider(server_token='test-token', from_email='noreply@example.com')

    with pytest.raises(ValueError):
        provider.send('victim@x.com\r\nBcc: attacker@evil.com', 'Subject', 'Body')

    assert calls == []


def test_postmark_provider_used_via_send_when_configured(app, monkeypatch):
    # End-to-end through get_provider()/_send() rather than constructing
    # PostmarkEmailProvider directly, to prove the config wiring actually
    # takes effect for a real POST /api/apply-triggered send.
    app.config['EMAIL_PROVIDER'] = 'postmark'
    app.config['POSTMARK_SERVER_TOKEN'] = 'test-token'
    app.config['EMAIL_FROM_ADDRESS'] = 'noreply@example.com'
    calls = []
    monkeypatch.setattr(
        email_sender.requests, 'post',
        lambda url, **kw: (calls.append(kw) or _FakePostmarkResponse()),
    )

    with app.app_context():
        assert email_sender._send('jane@example.com', 'Subject', 'Body') is True

    assert len(calls) == 1


# --- Resend send ---------------------------------------------------------------

def test_resend_provider_sends_successfully(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return _FakeResendResponse(status_code=200)

    monkeypatch.setattr(email_sender.requests, 'post', fake_post)
    provider = email_sender.ResendEmailProvider(api_key='test-key', from_email='noreply@example.com')

    provider.send('jane@example.com', 'Subject line', 'Body text')

    assert len(calls) == 1
    url, headers, payload, timeout = calls[0]
    assert url == email_sender.RESEND_SEND_URL
    assert headers['Authorization'] == 'Bearer test-key'
    assert payload['from'] == 'noreply@example.com'
    assert payload['to'] == ['jane@example.com']
    assert payload['subject'] == 'Subject line'
    assert payload['text'] == 'Body text'
    assert timeout == email_sender.RESEND_TIMEOUT_SECONDS


def test_resend_provider_rejects_implausible_email(monkeypatch):
    # Should never even build the request - no requests.post call at all.
    calls = []
    monkeypatch.setattr(email_sender.requests, 'post', lambda *a, **kw: calls.append(1))
    provider = email_sender.ResendEmailProvider(api_key='test-key', from_email='noreply@example.com')

    with pytest.raises(ValueError):
        provider.send('victim@x.com\r\nBcc: attacker@evil.com', 'Subject', 'Body')

    assert calls == []


def test_resend_provider_raises_generic_http_error_without_a_useful_error_message(monkeypatch):
    # No 'message' in the body (e.g. a plain proxy error page on an outage) -
    # falls back to requests' own error rather than a RuntimeError.
    monkeypatch.setattr(email_sender.requests, 'post', lambda url, **kw: _FakeResendResponse(status_code=500))
    provider = email_sender.ResendEmailProvider(api_key='test-key', from_email='noreply@example.com')

    with pytest.raises(email_sender.requests.HTTPError):
        provider.send('jane@example.com', 'Subject', 'Body')


def test_resend_provider_surfaces_error_message_on_non_2xx_status(monkeypatch):
    # Resend's own rejection reason must not get lost behind
    # raise_for_status()'s generic "422 Client Error" - same regression
    # coverage as Postmark's equivalent test above.
    monkeypatch.setattr(
        email_sender.requests, 'post',
        lambda url, **kw: _FakeResendResponse(status_code=422, message='Invalid from field', name='validation_error'),
    )
    provider = email_sender.ResendEmailProvider(api_key='test-key', from_email='noreply@example.com')

    with pytest.raises(RuntimeError, match='Invalid from field'):
        provider.send('jane@example.com', 'Subject', 'Body')


def test_resend_provider_used_via_send_when_configured(app, monkeypatch):
    # End-to-end through get_provider()/_send() rather than constructing
    # ResendEmailProvider directly, to prove the config wiring actually
    # takes effect for a real POST /api/apply-triggered send.
    app.config['EMAIL_PROVIDER'] = 'resend'
    app.config['RESEND_API_KEY'] = 'test-key'
    app.config['EMAIL_FROM_ADDRESS'] = 'noreply@example.com'
    calls = []
    monkeypatch.setattr(
        email_sender.requests, 'post',
        lambda url, **kw: (calls.append(kw) or _FakeResendResponse()),
    )

    with app.app_context():
        assert email_sender._send('jane@example.com', 'Subject', 'Body') is True

    assert len(calls) == 1


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

def test_send_rejects_implausible_email_before_reaching_a_provider(spy_provider):
    with pytest.raises(ValueError):
        email_sender._send('victim@x.com\r\nBcc: attacker@evil.com', 'Subject', 'Body')

    assert spy_provider.sent == []  # never reached the provider


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
        meeting_link='https://v.ringcentral.com/join/199431569', confirmation_code='7X4KMPQ2R',
        status_url='https://example.com/status?code=7X4KMPQ2R',
    )

    assert result is True
    to_email, subject, body = spy_provider.sent[0]
    assert to_email == 'jane@example.com'
    assert 'CHHA' in subject and 'Virtual interview' in subject
    assert 'https://v.ringcentral.com/join/199431569' in body
    assert '7X4KMPQ2R' in body
    assert 'https://example.com/status?code=7X4KMPQ2R' in body

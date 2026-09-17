"""recaptcha.py's verify_recaptcha - the one real network call, isolated so
routes/auth.py's login() tests can monkeypatch just this (see
test_auth.py) rather than requests itself."""
import pytest
import requests

from recaptcha import verify_recaptcha


class _FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json_body = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} error')

    def json(self):
        return self._json_body


def test_verify_recaptcha_true_on_success(monkeypatch):
    calls = []
    monkeypatch.setattr(
        requests, 'post',
        lambda url, data, timeout: calls.append((url, data, timeout)) or _FakeResponse({'success': True}),
    )
    assert verify_recaptcha('secret-abc', 'token-123', remote_ip='1.2.3.4') is True
    url, data, timeout = calls[0]
    assert url == 'https://www.google.com/recaptcha/api/siteverify'
    assert data == {'secret': 'secret-abc', 'response': 'token-123', 'remoteip': '1.2.3.4'}
    assert timeout == 10


def test_verify_recaptcha_false_when_google_rejects_it(monkeypatch):
    monkeypatch.setattr(
        requests, 'post', lambda url, data, timeout: _FakeResponse({'success': False, 'error-codes': ['timeout-or-duplicate']}),
    )
    assert verify_recaptcha('secret-abc', 'stale-token') is False


def test_verify_recaptcha_omits_remote_ip_when_not_given(monkeypatch):
    calls = []
    monkeypatch.setattr(
        requests, 'post', lambda url, data, timeout: calls.append(data) or _FakeResponse({'success': True}),
    )
    verify_recaptcha('secret-abc', 'token-123')
    assert 'remoteip' not in calls[0]


def test_verify_recaptcha_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(requests, 'post', lambda url, data, timeout: _FakeResponse({}, status_code=500))
    with pytest.raises(requests.RequestException):
        verify_recaptcha('secret-abc', 'token-123')

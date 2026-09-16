"""ringcentral_video.py's own logic: token refresh (mirrors
test_calendar_auth.py's Microsoft equivalent), meeting creation, and
recording retrieval/download. Nothing here talks to a real RingCentral API
- the low-level HTTP calls (_create_bridge_request, _get_meeting_request)
are monkeypatched, same pattern as test_calendar_availability.py."""
from datetime import datetime, timedelta

import pytest

import ringcentral_video
from ringcentral_video import (
    RingCentralNotConnectedError,
    create_meeting,
    decrypt_token,
    download_recording,
    encrypt_token,
    get_meeting_recording_url,
    get_valid_access_token,
)
from models import RingCentralConnection, db


# --- get_valid_access_token -----------------------------------------------

def test_get_valid_access_token_raises_when_never_connected(app, user):
    with app.app_context():
        with pytest.raises(RingCentralNotConnectedError):
            get_valid_access_token(user)


def test_get_valid_access_token_returns_cached_token_without_refreshing(app, user, monkeypatch):
    def _fail_if_called(refresh_token):
        raise AssertionError('should not refresh when the cached token is still valid')
    monkeypatch.setattr(ringcentral_video, '_refresh_access_token', _fail_if_called)

    with app.app_context():
        db.session.add(RingCentralConnection(
            user_id=user.id, account_email='interviewer@rc.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
            access_token='still-good', token_expiry=datetime.utcnow() + timedelta(minutes=30),
        ))
        db.session.commit()
        assert get_valid_access_token(user) == 'still-good'


def test_get_valid_access_token_refreshes_when_expired(app, user, monkeypatch):
    monkeypatch.setattr(
        ringcentral_video, '_refresh_access_token',
        lambda refresh_token: {'access_token': 'refreshed-token', 'expires_in': 3600},
    )
    with app.app_context():
        connection = RingCentralConnection(
            user_id=user.id, account_email='interviewer@rc.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
            access_token='stale-token', token_expiry=datetime.utcnow() - timedelta(minutes=5),
        )
        db.session.add(connection)
        db.session.commit()

        assert get_valid_access_token(user) == 'refreshed-token'
        refreshed = db.session.get(RingCentralConnection, connection.id)
        assert refreshed.access_token == 'refreshed-token'


def test_get_valid_access_token_always_persists_the_rotated_refresh_token(app, user, monkeypatch):
    """Unlike Microsoft (only sometimes rotates), RingCentral always issues
    a new refresh token on use - the new one must be persisted every time."""
    monkeypatch.setattr(
        ringcentral_video, '_refresh_access_token',
        lambda refresh_token: {
            'access_token': 'refreshed-token', 'expires_in': 3600, 'refresh_token': 'rotated-refresh',
        },
    )
    with app.app_context():
        connection = RingCentralConnection(
            user_id=user.id, account_email='interviewer@rc.com',
            encrypted_refresh_token=encrypt_token('original-refresh'),
            access_token='stale-token', token_expiry=datetime.utcnow() - timedelta(minutes=5),
        )
        db.session.add(connection)
        db.session.commit()

        get_valid_access_token(user)
        refreshed = db.session.get(RingCentralConnection, connection.id)
        assert decrypt_token(refreshed.encrypted_refresh_token) == 'rotated-refresh'


# --- create_meeting ---------------------------------------------------------

def test_create_meeting_returns_id_and_join_url(app, user, monkeypatch):
    monkeypatch.setattr(ringcentral_video, 'get_valid_access_token', lambda u: 'valid-token')
    monkeypatch.setattr(
        ringcentral_video, '_create_bridge_request',
        lambda access_token, name: {'id': 'meeting-123', 'discovery': {'web': 'https://v.ringcentral.com/join/xyz'}},
    )
    with app.app_context():
        meeting_id, join_url = create_meeting(user, topic='CHHA Interview - Jane Doe')
    assert meeting_id == 'meeting-123'
    assert join_url == 'https://v.ringcentral.com/join/xyz'


def test_create_meeting_propagates_not_connected(app, user):
    with app.app_context():
        with pytest.raises(RingCentralNotConnectedError):
            create_meeting(user, topic='CHHA Interview - Jane Doe')


# --- recording retrieval -----------------------------------------------------

def test_get_meeting_recording_url_returns_the_first_recording(app, user, monkeypatch):
    monkeypatch.setattr(ringcentral_video, 'get_valid_access_token', lambda u: 'valid-token')
    monkeypatch.setattr(
        ringcentral_video, '_get_meeting_request',
        lambda access_token, meeting_id: {
            'id': meeting_id,
            'recordings': [{'id': 'rec-1', 'url': 'https://media.ringcentral.com/rcvideo/v1/recordings/abc'}],
        },
    )
    with app.app_context():
        url = get_meeting_recording_url(user, 'meeting-123')
    assert url == 'https://media.ringcentral.com/rcvideo/v1/recordings/abc'


def test_get_meeting_recording_url_is_none_when_no_recording_yet(app, user, monkeypatch):
    monkeypatch.setattr(ringcentral_video, 'get_valid_access_token', lambda u: 'valid-token')
    monkeypatch.setattr(
        ringcentral_video, '_get_meeting_request',
        lambda access_token, meeting_id: {'id': meeting_id, 'recordings': []},
    )
    with app.app_context():
        assert get_meeting_recording_url(user, 'meeting-123') is None


def test_get_meeting_recording_url_is_none_when_meeting_not_found(app, user, monkeypatch):
    monkeypatch.setattr(ringcentral_video, 'get_valid_access_token', lambda u: 'valid-token')
    monkeypatch.setattr(ringcentral_video, '_get_meeting_request', lambda access_token, meeting_id: None)
    with app.app_context():
        assert get_meeting_recording_url(user, 'meeting-123') is None


def test_download_recording_returns_raw_bytes(app, user, monkeypatch):
    monkeypatch.setattr(ringcentral_video, 'get_valid_access_token', lambda u: 'valid-token')

    class _FakeResponse:
        content = b'fake-video-bytes'
        def raise_for_status(self):
            pass

    captured = {}

    def _fake_get(url, headers=None, timeout=None):
        captured['url'] = url
        captured['headers'] = headers
        return _FakeResponse()

    monkeypatch.setattr(ringcentral_video.requests, 'get', _fake_get)

    with app.app_context():
        data = download_recording(user, 'https://media.ringcentral.com/rcvideo/v1/recordings/abc')

    assert data == b'fake-video-bytes'
    assert captured['headers']['Authorization'] == 'Bearer valid-token'

"""microsoft_calendar.py's availability/booking additions: slot generation,
get_free_slots' busy/lead-time filtering, create_event's request body
(including embedding the interviewer's own RingCentral link as the event's
location), and delete_event. Nothing here talks to real
Microsoft Graph APIs - the low-level *_request functions are monkeypatched
out, the same way test_calendar_auth.py mocks
exchange_code_for_tokens/fetch_microsoft_email.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import microsoft_calendar
from microsoft_calendar import CalendarNotConnectedError, encrypt_token
from models import CalendarConnection, Organization, db

# Always well in the future relative to whenever the suite actually runs, so
# MIN_LEAD_TIME_HOURS filtering never accidentally excludes these.
FAR_FUTURE_YEAR = 2035


@pytest.fixture
def connected_user(app, user):
    with app.app_context():
        db.session.add(CalendarConnection(
            user_id=user.id, account_email='interviewer@outlook.com',
            encrypted_refresh_token=encrypt_token('refresh-456'),
            access_token='valid-access-token', token_expiry=datetime.utcnow() + timedelta(minutes=30),
        ))
        db.session.commit()
    return user


# --- _candidate_slot_windows --------------------------------------------------

ALL_WEEKDAYS = set(range(7))


def test_candidate_slot_windows_covers_working_hours_at_the_given_duration():
    slots = microsoft_calendar._candidate_slot_windows(
        window_days=0, duration_minutes=60, working_hours_start=9, working_hours_end=17,
        allowed_weekdays=ALL_WEEKDAYS, tz=ZoneInfo('UTC'),
    )

    assert len(slots) == 8  # 9-10, 10-11, ..., 16-17
    first_start, first_end = slots[0]
    assert first_start.hour == 9 and first_end.hour == 10
    last_start, last_end = slots[-1]
    assert last_start.hour == 16 and last_end.hour == 17


def test_candidate_slot_windows_spans_multiple_days():
    slots = microsoft_calendar._candidate_slot_windows(
        window_days=2, duration_minutes=480, working_hours_start=9, working_hours_end=17,
        allowed_weekdays=ALL_WEEKDAYS, tz=ZoneInfo('UTC'),
    )
    assert len(slots) == 3  # one full-working-day slot per day, 3 days (0..2 inclusive)


def test_candidate_slot_windows_skips_disallowed_weekdays():
    # A wide enough window (14 days) to guarantee it spans every weekday at
    # least once, regardless of which day "today" happens to be when the
    # suite runs.
    monday_only = microsoft_calendar._candidate_slot_windows(
        window_days=13, duration_minutes=480, working_hours_start=9, working_hours_end=17,
        allowed_weekdays={0}, tz=ZoneInfo('UTC'),
    )
    assert len(monday_only) == 2  # 14-day window contains exactly 2 Mondays
    assert all(start.weekday() == 0 for start, _end in monday_only)


# --- get_free_slots reads settings from Organization ---------------------------

def test_get_free_slots_uses_organization_scheduling_settings(app, connected_user, monkeypatch):
    """Confirms get_free_slots actually plumbs Organization.scheduling_* into
    _candidate_slot_windows, rather than something stale/hardcoded - the
    settings themselves (working hours math, weekday filtering) are covered
    directly against _candidate_slot_windows above."""
    with app.app_context():
        db.session.add(Organization(
            name='Test Org', scheduling_timezone='America/New_York',
            scheduling_working_hours_start=10, scheduling_working_hours_end=14,
            scheduling_days=[2],  # Wednesday only
        ))
        db.session.commit()

    captured = {}

    def _capture(window_days, duration_minutes, working_hours_start, working_hours_end, allowed_weekdays, tz):
        captured.update(
            working_hours_start=working_hours_start, working_hours_end=working_hours_end,
            allowed_weekdays=allowed_weekdays, tz=str(tz),
        )
        return []

    monkeypatch.setattr(microsoft_calendar, '_candidate_slot_windows', _capture)

    with app.app_context():
        microsoft_calendar.get_free_slots(connected_user, duration_minutes=30, window_days=7)

    assert captured == {
        'working_hours_start': 10, 'working_hours_end': 14, 'allowed_weekdays': {2}, 'tz': 'America/New_York',
    }


def test_get_free_slots_falls_back_to_defaults_with_no_organization_row(app, connected_user, monkeypatch):
    captured = {}

    def _capture(window_days, duration_minutes, working_hours_start, working_hours_end, allowed_weekdays, tz):
        captured.update(
            working_hours_start=working_hours_start, working_hours_end=working_hours_end,
            allowed_weekdays=allowed_weekdays, tz=str(tz),
        )
        return []

    monkeypatch.setattr(microsoft_calendar, '_candidate_slot_windows', _capture)

    with app.app_context():
        microsoft_calendar.get_free_slots(connected_user, duration_minutes=30, window_days=7)

    assert captured == {
        'working_hours_start': 9, 'working_hours_end': 17, 'allowed_weekdays': {0, 1, 2, 3, 4}, 'tz': 'UTC',
    }


def test_get_free_slots_raises_when_never_connected(app, user):
    with app.app_context():
        with pytest.raises(CalendarNotConnectedError):
            microsoft_calendar.get_free_slots(user, duration_minutes=30, window_days=1)


def test_get_free_slots_excludes_busy_blocks(app, connected_user, monkeypatch):
    fixed_slots = [
        (datetime(FAR_FUTURE_YEAR, 1, 1, 9, 0), datetime(FAR_FUTURE_YEAR, 1, 1, 9, 30)),
        (datetime(FAR_FUTURE_YEAR, 1, 1, 9, 30), datetime(FAR_FUTURE_YEAR, 1, 1, 10, 0)),
        (datetime(FAR_FUTURE_YEAR, 1, 1, 10, 0), datetime(FAR_FUTURE_YEAR, 1, 1, 10, 30)),
    ]
    monkeypatch.setattr(microsoft_calendar, '_candidate_slot_windows', lambda *a, **k: fixed_slots)
    # Busy for the middle slot only - overlaps [9:30, 10:00).
    monkeypatch.setattr(
        microsoft_calendar, '_get_schedule_request',
        lambda access_token, account_email, time_min, time_max: [
            (datetime(FAR_FUTURE_YEAR, 1, 1, 9, 45), datetime(FAR_FUTURE_YEAR, 1, 1, 9, 50)),
        ],
    )

    with app.app_context():
        result = microsoft_calendar.get_free_slots(connected_user, duration_minutes=30, window_days=1)

    assert result == [fixed_slots[0], fixed_slots[2]]


def test_get_free_slots_excludes_slots_inside_the_lead_time_window(app, connected_user, monkeypatch):
    too_soon = datetime.utcnow() + timedelta(minutes=30)  # inside MIN_LEAD_TIME_HOURS
    plenty_of_notice = datetime(FAR_FUTURE_YEAR, 1, 1, 9, 0)
    fixed_slots = [
        (too_soon, too_soon + timedelta(minutes=30)),
        (plenty_of_notice, plenty_of_notice + timedelta(minutes=30)),
    ]
    monkeypatch.setattr(microsoft_calendar, '_candidate_slot_windows', lambda *a, **k: fixed_slots)
    monkeypatch.setattr(microsoft_calendar, '_get_schedule_request', lambda *a, **k: [])

    with app.app_context():
        result = microsoft_calendar.get_free_slots(connected_user, duration_minutes=30, window_days=1)

    assert result == [fixed_slots[1]]


# --- create_event ---------------------------------------------------------------

RINGCENTRAL_LINK = 'https://v.ringcentral.com/join/199431569'


def test_create_event_embeds_the_meeting_link_as_location(app, connected_user, monkeypatch):
    """Interviews are conducted over RingCentral via the interviewer's own
    static link (User.personal_meeting_link, passed in by the caller - see
    routes/apply.py) - create_event itself no longer generates one (Teams/
    Google Meet/etc), it just puts the given link on the event so it's
    visible on the interviewer's own calendar."""
    captured = {}

    def _fake_request(access_token, body):
        captured['access_token'] = access_token
        captured['body'] = body
        return {'id': 'ms-event-123'}

    monkeypatch.setattr(microsoft_calendar, '_create_calendar_event_request', _fake_request)

    with app.app_context():
        event_id = microsoft_calendar.create_event(
            connected_user, summary='Interview - Jane', description='desc',
            start=datetime(FAR_FUTURE_YEAR, 1, 1, 9, 0), end=datetime(FAR_FUTURE_YEAR, 1, 1, 9, 30),
            attendee_email='jane@example.com', meeting_link=RINGCENTRAL_LINK,
        )

    assert event_id == 'ms-event-123'
    assert captured['access_token'] == 'valid-access-token'
    assert captured['body']['location'] == {'displayName': RINGCENTRAL_LINK}
    assert 'isOnlineMeeting' not in captured['body']
    assert captured['body']['attendees'] == [{'emailAddress': {'address': 'jane@example.com'}, 'type': 'required'}]


def test_create_event_omits_location_without_a_meeting_link(app, connected_user, monkeypatch):
    """An interviewer who hasn't set their RingCentral link yet - the event
    still gets created, just with no location."""
    captured = {}

    def _fake_request(access_token, body):
        captured['body'] = body
        return {'id': 'ms-event-456'}

    monkeypatch.setattr(microsoft_calendar, '_create_calendar_event_request', _fake_request)

    with app.app_context():
        event_id = microsoft_calendar.create_event(
            connected_user, summary='Interview', description='desc',
            start=datetime(FAR_FUTURE_YEAR, 1, 1, 9, 0), end=datetime(FAR_FUTURE_YEAR, 1, 1, 9, 30),
        )

    assert event_id == 'ms-event-456'
    assert 'location' not in captured['body']


def test_create_event_omits_attendees_when_no_attendee_email(app, connected_user, monkeypatch):
    captured = {}

    def _fake_request(access_token, body):
        captured['body'] = body
        return {'id': 'ms-event-789'}

    monkeypatch.setattr(microsoft_calendar, '_create_calendar_event_request', _fake_request)

    with app.app_context():
        microsoft_calendar.create_event(
            connected_user, summary='Interview', description='desc',
            start=datetime(FAR_FUTURE_YEAR, 1, 1, 9, 0), end=datetime(FAR_FUTURE_YEAR, 1, 1, 9, 30),
        )

    assert 'attendees' not in captured['body']


# --- delete_event ---------------------------------------------------------------

def test_delete_event_calls_the_low_level_request(app, connected_user, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        microsoft_calendar, '_delete_calendar_event_request',
        lambda access_token, event_id: captured.update(access_token=access_token, event_id=event_id),
    )

    with app.app_context():
        microsoft_calendar.delete_event(connected_user, 'ms-event-123')

    assert captured == {'access_token': 'valid-access-token', 'event_id': 'ms-event-123'}


# --- _parse_graph_datetime -------------------------------------------------------

def test_parse_graph_datetime_truncates_seven_digit_fractional_seconds():
    # Graph commonly returns 7 fractional-second digits, which
    # datetime.fromisoformat() rejects outright (it accepts at most 6).
    parsed = microsoft_calendar._parse_graph_datetime('2035-01-01T09:00:00.1234567')
    assert parsed == datetime(2035, 1, 1, 9, 0, 0, 123456)


def test_parse_graph_datetime_handles_no_fractional_seconds():
    parsed = microsoft_calendar._parse_graph_datetime('2035-01-01T09:00:00')
    assert parsed == datetime(2035, 1, 1, 9, 0, 0)

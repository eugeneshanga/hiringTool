from datetime import datetime, timezone


def parse_datetime(value, field_name='value'):
    """Parses an ISO-8601 datetime string (with or without a trailing 'Z' or
    UTC offset) and normalizes it to naive UTC — the storage convention every
    timestamp column in this app uses (see models.iso_utc for the read side
    of this contract). Raises ValueError with a user-facing message on bad
    input, so callers can just catch it and 400.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an ISO-8601 datetime string")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

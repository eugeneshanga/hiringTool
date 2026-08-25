"""Public, unauthenticated lookup of a booked interview - the status page
routes/apply.py's submit step redirects to, plus the "check back later" path
via confirmation code or phone number (see the goal doc's step 5).

Privacy note: a phone number is much lower-entropy than a confirmation code
(10ish digits vs. a 9-char code from a 56-character alphabet), so a phone
lookup is realistically guessable/enumerable in a way a code lookup isn't.
Two things bound that here: this endpoint is rate-limited by IP like
POST /api/apply is, and a phone match only ever considers interviews
actually booked through the public apply flow (Interview.confirmation_code
IS NOT NULL) - never a recruiter-created interview, which this endpoint has
no business exposing at all.
"""
import re
from datetime import datetime

from flask import Blueprint, jsonify, request

from extensions import limiter
from models import Candidate, Interview, iso_utc

status_bp = Blueprint('status', __name__)

# Below this many digits a "phone number" is too short to mean anything -
# reject rather than run a lookup that would just fail to match (or, worse,
# match too broadly against short/malformed stored values).
MIN_PHONE_DIGITS = 7


def _normalize_phone(value):
    """Digits only, last 10 - so '(555) 123-4567', '555-123-4567', and
    '15551234567' all compare equal. This app never normalizes phone at
    storage time (see models.Candidate), so comparison has to tolerate
    whatever formatting a candidate or recruiter typed in."""
    digits = re.sub(r'\D', '', value or '')
    return digits[-10:] if digits else ''


def _booked_interview_for_phone(phone):
    target = _normalize_phone(phone)
    if len(target) < MIN_PHONE_DIGITS:
        return None

    matching_candidate_ids = {
        c.id for c in Candidate.query.filter(Candidate.phone.isnot(None)).all()
        if _normalize_phone(c.display_phone) == target
    }
    if not matching_candidate_ids:
        return None

    booked = Interview.query.filter(
        Interview.confirmation_code.isnot(None),
        Interview.candidates.any(Candidate.id.in_(matching_candidate_ids)),
    ).all()
    if not booked:
        return None

    # Same "soonest upcoming, else most recently touched" heuristic as
    # Candidate._current_stage_summary() - a phone can match more than one
    # booking (a candidate who's applied to more than one job), so pick the
    # one most likely to be what they're checking on right now.
    now = datetime.utcnow()
    upcoming = [i for i in booked if i.scheduled_start >= now]
    return min(upcoming, key=lambda i: i.scheduled_start) if upcoming else max(booked, key=lambda i: i.scheduled_start)


@status_bp.route('/api/status', methods=['GET'])
@limiter.limit("20 per hour")
def get_status():
    code = (request.args.get('code') or '').strip()
    phone = (request.args.get('phone') or '').strip()
    if not code and not phone:
        return jsonify({"error": "code or phone is required"}), 400

    if code:
        interview = Interview.query.filter_by(confirmation_code=code).first()
    else:
        interview = _booked_interview_for_phone(phone)

    if not interview:
        return jsonify({"error": "no matching application found"}), 404

    candidate = interview.candidates[0] if interview.candidates else None
    return jsonify({
        "candidate_name": candidate.display_name if candidate else None,
        "job_title": interview.job.title if interview.job else None,
        "stage_name": interview.stage_name,
        "scheduled_start": iso_utc(interview.scheduled_start),
        "scheduled_end": iso_utc(interview.scheduled_end),
        "meeting_link": interview.meeting_link,
        "confirmation_code": interview.confirmation_code,
    }), 200

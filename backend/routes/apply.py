"""The public, unauthenticated apply flow - candidates never get their own
login (see ApplicationStatusPage / routes/status.py for the phone/
confirmation-code lookup they use instead to check status and upload
onboarding documents).

Three steps:
  POST /api/apply               - create the Candidate, save their screening
                                   answers, and auto-evaluate them (anti-abuse
                                   checks live here too - see below):
                                     qualified    -> email #1, the scheduling
                                                     link, sent right away.
                                     disqualified -> no scheduling link ever
                                                     goes out; a rejection
                                                     email goes out later
                                                     instead (see
                                                     scheduled_jobs.py).
  GET  /api/apply/<token>       - that job's title and open interview slots.
                                   Only ever reachable by a qualified
                                   candidate - see below.
  POST /api/apply/<token>/submit - atomic: book the slot, create the real
                                   calendar event, generate a confirmation
                                   code, send email #2.

application_token is only ever generated for a *qualified* candidate (see
apply() below) - a disqualified one has no token at all, not an unusable
one, so there's nothing here for GET/POST .../<token> to special-case: a
disqualified candidate's token is simply never issued, so those routes 404
for them exactly like any other unknown token would.

Which stage a candidate schedules against: the job's first MeetingStageTemplate
by sort_order, whichever type it is (see _scheduling_stage_for) - not
necessarily an interview-typed one, by design (simplest, deterministic
option discussed and picked over filtering by meeting_type).

Anti-abuse posture on POST /api/apply specifically: it's public and sends
email, so it's a spam target. Several checks there are deliberately
indistinguishable from a real, freshly-created application in their response
- a bot probing the endpoint should not be able to tell "your submission was
fake and silently dropped" from "you really just applied" by watching the
response - and that now extends to the qualified/disqualified outcome too,
for the same reason: the response never reveals which one happened, only
email does (see _generic_success_response). GET/POST .../<token> don't need
that treatment - the token itself is the secret (only someone holding the
emailed link reaches them), so honest 404/410/409s are fine there.
"""
import json
import os
from datetime import datetime, timedelta

import dns.resolver
import requests
from flask import Blueprint, current_app, jsonify, request

from dateutils import parse_datetime
from email_sender import is_plausible_email, send_confirmation_email, send_schedule_interview_email
from extensions import limiter
from file_storage import save_candidate_file
from microsoft_calendar import (
    CalendarNotConnectedError,
    CalendarTokenError,
    create_event,
    delete_event,
    get_free_slots,
)
from models import (
    Candidate,
    CandidateScreeningAnswer,
    CandidateStageProgress,
    Interview,
    Job,
    Organization,
    User,
    db,
    generate_application_token,
    generate_confirmation_code,
    is_email_blocked,
    iso_utc,
)

apply_bp = Blueprint('apply', __name__)


@apply_bp.route('/api/apply/jobs/<int:job_id>', methods=['GET'])
def get_public_job(job_id):
    """Minimal public job info for the apply form to render - deliberately
    a small, hand-picked contract rather than Job.to_dict() (which carries
    recruiter-side fields like candidate_count that have no business being
    public and could grow further without this endpoint in mind). Draft/
    Closed jobs 404 - not discoverable here, same as they're not offered
    through POST /api/apply."""
    job = Job.query.get(job_id)
    if not job or job.status != 'Published':
        return jsonify({"error": f"no open job with id {job_id}"}), 404
    # Org name is used in the apply form's EEO notice (see apply()) - read
    # directly rather than via organization.py's _get_organization() (which
    # auto-creates a default row) since a public, unauthenticated endpoint
    # shouldn't be the thing that first creates the org record; falling back
    # to a generic phrase covers that not-yet-set-up case instead.
    org = Organization.query.first()
    return jsonify({
        "id": job.id,
        "title": job.title,
        "location": job.location,
        "description": job.description,
        "highlights": job.highlights or [],
        "job_type": job.job_type or [],
        "min_salary": job.min_salary,
        "max_salary": job.max_salary,
        "salary_period": job.salary_period,
        "organization_name": org.name if org else "this organization",
        "screening_questions": [
            {"id": q.id, "question_text": q.question_text, "answer_options": q.answer_options or []}
            for q in job.screening_questions
        ],
    }), 200

# How long a generated application_token (and thus the emailed apply link)
# stays valid. Long enough to cover a candidate getting to it a few days
# late; short enough that a stale link from an old application eventually
# stops being live for the dedupe check below to key off of.
APPLICATION_TOKEN_LIFETIME_DAYS = 14

# Name of the honeypot field the (future) public apply form includes as a
# hidden input - invisible via CSS to a real person, but present in the DOM
# for a form-filling bot to stumble into. Deliberately a plausible-looking
# field name rather than something like "honeypot" that a bot's own
# heuristics might specifically know to skip.
HONEYPOT_FIELD = 'website'

# Short enough that a slow/unresponsive DNS server can't hang the request,
# per the anti-abuse requirement - this check is a defensive extra layer,
# not the primary defense, so it's fine for it to fail open (see
# _email_domain_has_mx) rather than block on a slow answer.
MX_LOOKUP_TIMEOUT_SECONDS = 2.0

# Enforced explicitly here rather than relying on config.py's
# MAX_CONTENT_LENGTH, which now has to be large enough to admit interview
# recordings (see routes/candidates.py) - a resume specifically should
# still be rejected well before that.
MAX_RESUME_SIZE_BYTES = 15 * 1024 * 1024  # 15MB


def _generic_success_response():
    """The response for POST /api/apply on every non-error path - honeypot
    trip, dedupe-hit, and a genuine fresh application all return exactly
    this, so nothing about the response lets a caller distinguish them (see
    module docstring). It intentionally carries no candidate/application
    details - those only ever go out over email, never in this response."""
    return jsonify({"status": "ok"}), 200


def _email_domain_has_mx(email):
    """True if the email's domain has at least one MX record. Fails open
    (True) on anything other than a definitive "this domain doesn't exist /
    accepts no mail" answer - a resolver timeout or other DNS hiccup
    shouldn't reject a real applicant on its own; the honeypot, blocklist,
    and rate limits below are the layers doing the real anti-abuse work."""
    domain = email.rsplit('@', 1)[-1]
    resolver = dns.resolver.Resolver()
    resolver.timeout = MX_LOOKUP_TIMEOUT_SECONDS
    resolver.lifetime = MX_LOOKUP_TIMEOUT_SECONDS
    try:
        resolver.resolve(domain, 'MX')
        return True
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return False
    except Exception:
        return True


def _email_job_rate_limit_key():
    """Key for the per-email-per-job daily limit - independent of the
    per-IP limit Flask-Limiter's default key_func provides, so a spammer
    rotating IPs against one email/job pair is still capped, and a burst of
    different applicants behind one IP (e.g. a shared office network) isn't
    penalized for each other's submissions.

    Reads request.form, not get_json - POST /api/apply is multipart/form-data
    now (it carries the resume file), not JSON."""
    email = (request.form.get('email') or '').strip().lower()
    job_id = request.form.get('job_id')
    return f'{email}:{job_id}'


def _parse_required_yes_no(value):
    """Parses a required yes/no form field ('yes'/'no', case-insensitive)
    into True/False, or None if missing/unrecognized. None is always a
    validation error at the call site - unlike work_authorized/
    requires_visa_sponsorship being nullable in the database (for candidates
    who didn't come through this form), the public form itself requires an
    answer to both, same as it requires a resume."""
    if not value:
        return None
    value = value.strip().lower()
    if value == 'yes':
        return True
    if value == 'no':
        return False
    return None


def _is_qualifying_answer(question, answer_text):
    """A free-text question (no answer_options) has no defined criteria for
    disqualifying anyone - always treated as qualifying. A multiple-choice
    question disqualifies unless the given answer is exactly one of its
    qualified_answers (see ScreeningQuestion's docstring in models.py - this
    is the same qualifying/disqualifying mechanism the Pre-screen tab has
    always defined per question, just evaluated automatically here instead
    of read by a recruiter)."""
    if not question.answer_options:
        return True
    return answer_text in (question.qualified_answers or [])


@apply_bp.route('/api/apply', methods=['POST'])
@limiter.limit("15 per hour")
@limiter.limit("1 per day", key_func=_email_job_rate_limit_key)
def apply():
    # multipart/form-data, not JSON - request.form for text fields,
    # request.files for the resume. See MAX_RESUME_SIZE_BYTES below for size
    # enforcement - config.py's MAX_CONTENT_LENGTH is too high a ceiling to
    # rely on alone now that it also has to admit interview recordings.
    form = request.form

    # Honeypot: a real person never sees or fills this field, so any
    # non-empty value here is a bot. Blend into the generic success path
    # without touching the database, the filesystem, or sending anything.
    if (form.get(HONEYPOT_FIELD) or '').strip():
        return _generic_success_response()

    first_name = (form.get('first_name') or '').strip()
    last_name = (form.get('last_name') or '').strip()
    email = (form.get('email') or '').strip().lower()
    phone = (form.get('phone') or '').strip() or None
    address_line1 = (form.get('address_line1') or '').strip() or None
    city = (form.get('city') or '').strip() or None
    state = (form.get('state') or '').strip() or None
    postal_code = (form.get('postal_code') or '').strip() or None
    job_id = form.get('job_id')
    resume = request.files.get('resume')

    work_authorized = _parse_required_yes_no(form.get('work_authorized'))
    requires_visa_sponsorship = _parse_required_yes_no(form.get('requires_visa_sponsorship'))

    if not first_name or not last_name or not email or not job_id:
        return jsonify({"error": "first name, last name, email, and job_id are required"}), 400
    if not is_plausible_email(email):
        return jsonify({"error": "a valid email is required"}), 400
    if not resume or not resume.filename:
        return jsonify({"error": "a resume is required"}), 400
    resume.stream.seek(0, os.SEEK_END)
    resume_size = resume.stream.tell()
    resume.stream.seek(0)
    if resume_size > MAX_RESUME_SIZE_BYTES:
        max_mb = MAX_RESUME_SIZE_BYTES // (1024 * 1024)
        return jsonify({"error": f"that file is too large - please upload something under {max_mb}MB"}), 400
    if work_authorized is None or requires_visa_sponsorship is None:
        return jsonify({"error": "please answer both work-authorization questions"}), 400

    try:
        answers = json.loads(form.get('answers') or '[]')
    except (TypeError, ValueError):
        answers = None
    if not isinstance(answers, list):
        return jsonify({"error": "answers must be a list of {question_id, answer_text}"}), 400

    job = Job.query.get(job_id)
    if not job or job.status != 'Published':
        return jsonify({"error": f"no open job with id {job_id}"}), 400

    # Every one of the job's screening questions is mandatory - see
    # _is_qualifying_answer for what happens with the content of the
    # answers; this only checks that all of them were actually answered.
    # (ScreeningQuestion has no per-question "required" flag - unlike
    # OnboardingDocumentItem - so this applies uniformly to all of them.)
    valid_question_ids = {q.id for q in job.screening_questions}
    answers_by_question = {}
    for entry in answers:
        question_id = entry.get('question_id') if isinstance(entry, dict) else None
        if question_id not in valid_question_ids:
            return jsonify({"error": f"question {question_id} does not belong to this job"}), 400
        answers_by_question[question_id] = entry.get('answer_text')
    unanswered = [q for q in job.screening_questions if not (answers_by_question.get(q.id) or '').strip()]
    if unanswered:
        return jsonify({"error": "please answer all screening questions"}), 400

    if is_email_blocked(email):
        return jsonify({"error": "this email is not eligible to apply"}), 403

    if not _email_domain_has_mx(email):
        return jsonify({"error": "please double-check your email address"}), 400

    # Dedupe: an existing, still-live application for this email+job means
    # this candidate already has a valid apply link out there (or is mid
    # scheduling) - no-op rather than creating a second Candidate or sending
    # a second email. A previously-*disqualified* candidate is never "live"
    # here (see below - they never get an application_token at all), so
    # this doesn't block someone from re-applying after a rejection.
    existing = Candidate.query.filter_by(job_id=job_id, email=email).filter(
        Candidate.application_token.isnot(None),
        Candidate.application_token_expires_at > datetime.utcnow(),
    ).first()
    if existing:
        return _generic_success_response()

    candidate = Candidate(
        name=f"{first_name} {last_name}",
        email=email,
        phone=phone,
        job_id=job_id,
        city=city,
        state=state,
        address_line1=address_line1,
        postal_code=postal_code,
        work_authorized=work_authorized,
        requires_visa_sponsorship=requires_visa_sponsorship,
        source=(form.get('source') or 'Public application'),
    )
    db.session.add(candidate)
    db.session.commit()

    for question_id, answer_text in answers_by_question.items():
        db.session.add(CandidateScreeningAnswer(
            candidate_id=candidate.id, question_id=question_id, answer_text=answer_text,
        ))
    db.session.commit()

    # The resume needs candidate.id (file_storage.py keys uploads by it), so
    # this can only happen after the row above is committed - if it fails,
    # the candidate already exists without a resume attached rather than not
    # existing at all. Logged and treated as best-effort for the same reason
    # the email sends below are: the application itself already succeeded.
    try:
        original_filename, stored_filename = save_candidate_file(candidate.id, resume)
        candidate.resume_original_filename = original_filename
        candidate.resume_stored_filename = stored_filename
        db.session.commit()
    except Exception:
        current_app.logger.exception("Failed to save resume for candidate %s", candidate.id)

    qualified = all(_is_qualifying_answer(q, answers_by_question.get(q.id)) for q in job.screening_questions)

    if qualified:
        # Only a qualified candidate ever gets a live application_token -
        # see the module docstring for why that alone is enough to keep a
        # disqualified candidate away from the scheduling routes, with no
        # special-casing needed there.
        candidate.application_token = generate_application_token()
        candidate.application_token_expires_at = datetime.utcnow() + timedelta(days=APPLICATION_TOKEN_LIFETIME_DAYS)
        db.session.commit()

        # Best-effort: the candidate row is already committed, so a
        # notification failure here shouldn't turn a successful application
        # into a 500 for them - log and move on rather than letting it
        # propagate.
        try:
            apply_url = f"{current_app.config['FRONTEND_BASE_URL']}/apply/schedule/{candidate.application_token}"
            send_schedule_interview_email(
                to_email=candidate.email,
                candidate_name=candidate.name,
                job_title=job.title,
                apply_url=apply_url,
                expires_at=candidate.application_token_expires_at,
            )
        except Exception:
            current_app.logger.exception(
                "Failed to send schedule-interview email for candidate %s", candidate.id
            )
    else:
        # No email sent inline here - scheduled_jobs.send_due_rejection_emails
        # picks this up once REJECTION_EMAIL_DELAY_MINUTES has passed. stage
        # flips to 'Rejected' immediately though, so a recruiter browsing the
        # Candidates list sees the real outcome right away even before the
        # email goes out.
        candidate.stage = 'Rejected'
        candidate.disqualified_at = datetime.utcnow()
        db.session.commit()

    return _generic_success_response()


# --- prescreen + scheduling page ---------------------------------------------

def _scheduling_stage_for(job):
    """The MeetingStageTemplate the public apply flow schedules against -
    the job's first stage by sort_order, whatever type it is. None if the
    job has no stages defined yet."""
    templates = sorted(job.meeting_stage_templates, key=lambda t: (t.sort_order, t.id))
    return templates[0] if templates else None


def _available_slots_for_stage(stage):
    """(start, end) tuples open for booking against `stage`, or [] if the
    stage can't be scheduled against yet (no interviewer assigned, no
    duration set, interviewer hasn't connected a calendar) or Microsoft
    Graph is unreachable right now - a public candidate-facing page shows
    "no slots" rather than a 500 in every one of those cases; see
    microsoft_calendar.get_free_slots."""
    if not stage or not stage.interviewer_user_id or not stage.duration_minutes:
        return []
    interviewer = User.query.get(stage.interviewer_user_id)
    if not interviewer:
        return []
    try:
        return get_free_slots(interviewer, stage.duration_minutes, stage.scheduling_window_days)
    except (CalendarNotConnectedError, CalendarTokenError, requests.RequestException):
        current_app.logger.warning(
            "Could not fetch calendar availability for meeting stage %s (interviewer user %s)",
            stage.id, stage.interviewer_user_id,
        )
        return []


def _application_lookup_or_error(token):
    """Shared GET/submit prelude: the Candidate for `token`, or (None,
    error_response) if the token is unknown/expired. Doesn't check
    candidate.scheduled - GET and submit treat "already scheduled"
    differently (see their docstrings), so that's left to each caller."""
    candidate = Candidate.query.filter_by(application_token=token).first()
    if not candidate:
        return None, (jsonify({"error": "invalid application link"}), 404)
    if candidate.application_token_expires_at and candidate.application_token_expires_at < datetime.utcnow():
        return None, (jsonify({"error": "this application link has expired"}), 410)
    if not candidate.job:
        return None, (jsonify({"error": "this application is no longer associated with an open job"}), 404)
    return candidate, None


@apply_bp.route('/api/apply/<token>', methods=['GET'])
def get_application(token):
    candidate, error = _application_lookup_or_error(token)
    if error:
        return error
    job = candidate.job
    # Used in the schedule page's header, same as get_public_job's - see
    # that route's comment on why this reads Organization directly rather
    # than via organization.py's auto-creating _get_organization().
    org = Organization.query.first()
    organization_name = org.name if org else "this organization"

    if candidate.scheduled:
        # The interview this candidate booked through this exact flow -
        # confirmation_code is only ever set by submit_application, so this
        # never picks up an unrelated recruiter-created interview.
        booked = next((i for i in candidate.interviews if i.confirmation_code), None)
        return jsonify({
            "job_title": job.title,
            "organization_name": organization_name,
            "already_scheduled": True,
            "stage_name": booked.stage_name if booked else None,
            "scheduled_start": iso_utc(booked.scheduled_start) if booked else None,
            "scheduled_end": iso_utc(booked.scheduled_end) if booked else None,
            "meeting_link": booked.meeting_link if booked else None,
            "confirmation_code": booked.confirmation_code if booked else None,
        }), 200

    stage = _scheduling_stage_for(job)
    return jsonify({
        "job_title": job.title,
        "organization_name": organization_name,
        "already_scheduled": False,
        "stage_name": stage.stage_name if stage else None,
        "meeting_type": stage.meeting_type if stage else None,
        "duration_minutes": stage.duration_minutes if stage else None,
        "available_slots": [
            {"start": iso_utc(start), "end": iso_utc(end)}
            for start, end in _available_slots_for_stage(stage)
        ],
    }), 200


def _unique_confirmation_code():
    """generate_confirmation_code() isn't unique by construction (see its
    docstring) - retry a few times on the astronomically unlikely collision
    rather than trusting a single draw, since the column is UNIQUE."""
    for _ in range(5):
        code = generate_confirmation_code()
        if not Interview.query.filter_by(confirmation_code=code).first():
            return code
    raise RuntimeError("could not generate a unique confirmation code after 5 attempts")


@apply_bp.route('/api/apply/<token>/submit', methods=['POST'])
def submit_application(token):
    candidate, error = _application_lookup_or_error(token)
    if error:
        return error
    if candidate.scheduled:
        return jsonify({"error": "this application has already been scheduled"}), 409

    job = candidate.job
    stage = _scheduling_stage_for(job)
    interviewer = User.query.get(stage.interviewer_user_id) if stage and stage.interviewer_user_id else None
    if not stage or not stage.duration_minutes or not interviewer:
        return jsonify({"error": "this job isn't open for scheduling right now"}), 400

    data = request.get_json(silent=True) or {}
    try:
        slot_start = parse_datetime(data.get('slot_start'), 'slot_start')
        slot_end = parse_datetime(data.get('slot_end'), 'slot_end')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Re-check the slot is still free right now - the list the candidate saw
    # from GET /api/apply/<token> could be stale by the time they submit,
    # either because someone else booked it or the interviewer's calendar
    # changed in the meantime.
    try:
        current_slots = get_free_slots(interviewer, stage.duration_minutes, stage.scheduling_window_days)
    except (CalendarNotConnectedError, CalendarTokenError, requests.RequestException):
        return jsonify({"error": "scheduling is temporarily unavailable - please try again shortly"}), 503
    if (slot_start, slot_end) not in current_slots:
        return jsonify({"error": "that time is no longer available - please pick another"}), 409

    # The interviewer's own static RingCentral link, not one generated
    # per-event by the calendar provider - see microsoft_calendar.py's
    # module docstring. None if they haven't set one on their Profile yet.
    meeting_link = interviewer.personal_meeting_link

    # Create the real calendar event before writing anything to our own DB -
    # if this fails, nothing below has happened yet, so there's nothing here
    # to roll back.
    try:
        calendar_event_id = create_event(
            interviewer,
            summary=f"{stage.stage_name} - {candidate.name}",
            description=f"{job.title} - {stage.stage_name} interview with {candidate.name} ({candidate.email})",
            start=slot_start, end=slot_end, attendee_email=candidate.email,
            meeting_link=meeting_link,
        )
    except Exception:
        current_app.logger.exception("Failed to create calendar event for candidate %s", candidate.id)
        return jsonify({"error": "scheduling is temporarily unavailable - please try again shortly"}), 503

    confirmation_code = _unique_confirmation_code()
    try:
        interview = Interview(
            job_id=job.id,
            meeting_stage_template_id=stage.id,
            stage_name=stage.stage_name,
            meeting_type='Interview',
            location=meeting_link,
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            confirmation_code=confirmation_code,
            meeting_link=meeting_link,
            calendar_event_id=calendar_event_id,
        )
        interview.candidates.append(candidate)
        db.session.add(interview)

        # Mirrors interviews.py's enroll_candidate: booking = the Interview
        # stage of the pipeline, and this stage's progress row reflects the
        # same schedule so the candidate's own page/current_stage agree with it.
        candidate.scheduled = True
        candidate.stage = 'Interview'
        db.session.add(CandidateStageProgress(
            candidate_id=candidate.id, meeting_stage_template_id=stage.id,
            status='Upcoming', scheduled_at=slot_start, location=meeting_link,
        ))

        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to persist booking after creating calendar event %s for candidate %s - "
            "attempting to delete the orphaned event", calendar_event_id, candidate.id,
        )
        try:
            delete_event(interviewer, calendar_event_id)
        except Exception:
            current_app.logger.exception("Also failed to clean up orphaned calendar event %s", calendar_event_id)
        return jsonify({"error": "something went wrong while booking - please try again"}), 500

    status_url = f"{current_app.config['FRONTEND_BASE_URL']}/status?code={confirmation_code}"
    try:
        send_confirmation_email(
            to_email=candidate.email, candidate_name=candidate.name, job_title=job.title,
            stage_name=stage.stage_name, scheduled_start=slot_start, meeting_link=meeting_link,
            confirmation_code=confirmation_code, status_url=status_url,
        )
    except Exception:
        current_app.logger.exception("Failed to send confirmation email for candidate %s", candidate.id)

    return jsonify({
        "confirmation_code": confirmation_code,
        "meeting_link": meeting_link,
        "scheduled_start": iso_utc(slot_start),
        "scheduled_end": iso_utc(slot_end),
        "status_url": status_url,
    }), 201

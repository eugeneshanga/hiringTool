"""Public, unauthenticated lookup of a booked interview - the status page
routes/apply.py's submit step redirects to, plus the "check back later" path
via confirmation code (see the goal doc's step 5). Also the only place a
candidate ever interacts with the app after applying: there's no candidate
login (see models.py's Candidate.display_name docstring for the removed
CandidateAccount) - the same code lookup that shows status here also gates
uploading onboarding documents (POST /api/status/documents), and a
candidate who lost their code entirely can get it re-emailed by POST
/api/status/resend-code (by email, not phone - see that route's docstring
for why), so a candidate never needs an account for any of this.

Privacy note: a confirmation code has enough entropy (9 chars from a
56-character alphabet) that a direct lookup returning the match (as GET
/api/status and POST /api/status/documents both do) is fine - guessing one
isn't realistic. That's specifically NOT true of lower-entropy identifiers
like a phone number or email address, which is why this file used to also
accept a phone number here and doesn't anymore (a phone lookup being
directly guessable/enumerable was an accepted, documented trade-off at the
time; email is at least as guessable and this was a deliberate call not to
carry the same trade-off forward for it). POST /api/status/resend-code is
the one place email comes in, and it never reflects a match (or lack of
one) back in its response at all - see that route's docstring - so it
doesn't reopen the same hole.
"""
import os
import zipfile
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from email_sender import is_plausible_email, send_confirmation_email
from extensions import limiter
from file_storage import delete_candidate_file, save_candidate_file
from models import Candidate, CandidateDocument, Interview, OnboardingDocumentItem, db, iso_utc

status_bp = Blueprint('status', __name__)

# Onboarding uploads through this public endpoint - deliberately narrower
# than what a recruiter can upload on a candidate's behalf (routes/
# candidates.py's upload_document has no type/size limit of its own beyond
# the app-wide MAX_CONTENT_LENGTH), since this one has no auth beyond the
# confirmation code.
ALLOWED_UPLOAD_EXTENSIONS = {'.pdf', '.docx', '.jpg', '.jpeg', '.png'}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10MB

# Checked in addition to the extension - a filename's extension is trivially
# spoofable, and this endpoint has no auth beyond the same confirmation-code
# check GET /api/status uses. .docx gets its own, stronger check below (it's
# a ZIP archive, and a raw byte-signature match can't tell a real .docx from
# any other renamed .zip).
_FILE_SIGNATURES = {
    '.pdf': (b'%PDF',),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
}


def _looks_like_docx(file_storage):
    """.docx is a ZIP archive with a specific internal layout - checking for
    word/document.xml is a real (if not airtight) distinction from an
    arbitrary renamed .zip, unlike a plain byte-signature match, which every
    ZIP-based format (docx, xlsx, pptx, plain .zip) shares."""
    try:
        with zipfile.ZipFile(file_storage) as zf:
            return 'word/document.xml' in zf.namelist()
    except zipfile.BadZipFile:
        return False
    finally:
        file_storage.seek(0)


def _file_matches_extension(file_storage, ext):
    if ext == '.docx':
        return _looks_like_docx(file_storage)
    signatures = _FILE_SIGNATURES.get(ext, ())
    header = file_storage.read(max((len(s) for s in signatures), default=0))
    file_storage.seek(0)
    return any(header.startswith(sig) for sig in signatures)


def _booked_interview_for_email(email):
    """Looks up a booked Interview by the email a candidate applied with -
    see POST /api/status/resend-code, the only place this is used (never a
    direct-lookup identifier the way the confirmation code is - see module
    docstring for why). is_plausible_email() is checked before this ever
    touches the database or a send: not really an injection concern here
    (this is a lookup, not a header), but there's no reason to run a query -
    or, worse, later hand a malformed value to send_confirmation_email -
    against something that was never a real email shape to begin with."""
    email = (email or '').strip().lower()
    if not is_plausible_email(email):
        return None

    matching_candidate_ids = {c.id for c in Candidate.query.filter_by(email=email).all()}
    if not matching_candidate_ids:
        return None

    booked = Interview.query.filter(
        Interview.confirmation_code.isnot(None),
        Interview.candidates.any(Candidate.id.in_(matching_candidate_ids)),
    ).all()
    if not booked:
        return None

    now = datetime.utcnow()
    upcoming = [i for i in booked if i.scheduled_start >= now]
    return min(upcoming, key=lambda i: i.scheduled_start) if upcoming else max(booked, key=lambda i: i.scheduled_start)


def _resolve_interview(code):
    """The one booked Interview a status-page visitor is looking up, by
    confirmation code - shared by GET /api/status and POST
    /api/status/documents, which both need to authenticate a visitor to
    exactly one Candidate the same way."""
    return Interview.query.filter_by(confirmation_code=code).first() if code else None


def _onboarding_checklist(candidate):
    """Every onboarding item across all of the candidate's job's stages
    (see Job.onboarding_items), each annotated with whatever's already been
    uploaded - identical shape/logic to routes/candidates.py's
    list_document_types, just reached by confirmation code instead of
    recruiter auth. Empty if the candidate has no job, or its stages define no
    onboarding items - the frontend hides the whole section in that case."""
    uploaded = {d.onboarding_item_id: d.to_dict() for d in candidate.documents}
    items = candidate.job.onboarding_items if candidate.job else []
    return [
        {
            "item_id": item.id,
            "description": item.description,
            "type": item.item_type,
            "required": item.required,
            "submission": uploaded.get(item.id),
        }
        for item in items
    ]


@status_bp.route('/api/status', methods=['GET'])
@limiter.limit("20 per hour")
def get_status():
    code = (request.args.get('code') or '').strip()
    if not code:
        return jsonify({"error": "code is required"}), 400

    interview = _resolve_interview(code)
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
        "onboarding_documents": _onboarding_checklist(candidate) if candidate else [],
    }), 200


@status_bp.route('/api/status/resend-code', methods=['POST'])
@limiter.limit("5 per hour")
def resend_confirmation_code():
    """Re-sends an existing booking's confirmation email to the address on
    file, for a candidate who lost the original. Deliberately never reveals
    in the response whether a match was found (see module docstring): the
    only observable effect of a hit is an email landing in that address's
    inbox, never anything in this response - unlike GET /api/status's code
    lookup, which returns the match directly, this can't be used as an
    email-enumeration oracle. Rate-limited tighter than that lookup too
    (5/hour vs. 20/hour) since a hit here spams a stranger's inbox, not
    just probes for a match - a real cost to a bystander, not just this
    app's own data."""
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()

    interview = _booked_interview_for_email(email)
    candidate = interview.candidates[0] if interview and interview.candidates else None
    if candidate:
        status_url = f"{current_app.config['FRONTEND_BASE_URL']}/status?code={interview.confirmation_code}"
        try:
            send_confirmation_email(
                to_email=candidate.display_email,
                candidate_name=candidate.display_name,
                job_title=interview.job.title if interview.job else '',
                stage_name=interview.stage_name,
                scheduled_start=interview.scheduled_start,
                meeting_link=interview.meeting_link,
                confirmation_code=interview.confirmation_code,
                status_url=status_url,
            )
        except Exception:
            # Best-effort, same as apply.py's own sends - a delivery failure
            # shouldn't turn into a 500, and must especially not turn into a
            # response that differs from the no-match case (see docstring).
            current_app.logger.exception(
                "Failed to resend confirmation email for interview %s", interview.id,
            )

    return jsonify({
        "message": "If that email matches an application with a scheduled interview, "
                   "we've sent the confirmation code to it.",
    }), 200


@status_bp.route('/api/status/documents', methods=['POST'])
@limiter.limit("10 per hour")
def upload_status_document():
    """Lets a candidate upload (or replace) one onboarding document without
    ever logging in - authenticated by the same confirmation-code check GET
    /api/status uses, sent as a form field alongside the file since this is
    multipart/form-data. Mirrors routes/candidates.py's upload_document
    (the recruiter-authenticated equivalent), plus the extension/magic-byte
    and size checks this public endpoint adds on top - see module-level
    ALLOWED_UPLOAD_EXTENSIONS/MAX_UPLOAD_SIZE_BYTES."""
    code = (request.form.get('code') or '').strip()
    if not code:
        return jsonify({"error": "code is required"}), 400

    interview = _resolve_interview(code)
    candidate = interview.candidates[0] if interview and interview.candidates else None
    if not candidate:
        return jsonify({"error": "no matching application found"}), 404

    try:
        item_id = int(request.form.get('onboarding_item_id', ''))
    except ValueError:
        return jsonify({"error": "onboarding_item_id is required"}), 400
    item = OnboardingDocumentItem.query.get(item_id)
    if not item or not candidate.job or item.meeting_stage_template.job_id != candidate.job_id:
        return jsonify({"error": "onboarding item does not belong to this application"}), 400

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"error": "file is required"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({"error": "only PDF, DOCX, JPG, and PNG files are accepted"}), 400

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        return jsonify({"error": f"that file is too large - please upload something under {max_mb}MB"}), 400

    if not _file_matches_extension(file.stream, ext):
        return jsonify({"error": f"that file doesn't look like a valid {ext.lstrip('.').upper()} file"}), 400

    existing = CandidateDocument.query.filter_by(
        candidate_id=candidate.id, onboarding_item_id=item.id,
    ).first()
    original_filename, stored_filename = save_candidate_file(candidate.id, file)

    if existing:
        delete_candidate_file(candidate.id, existing.stored_filename)
        existing.original_filename = original_filename
        existing.stored_filename = stored_filename
        document = existing
    else:
        document = CandidateDocument(
            candidate_id=candidate.id,
            onboarding_item_id=item.id,
            original_filename=original_filename,
            stored_filename=stored_filename,
        )
        db.session.add(document)

    db.session.commit()
    return jsonify(document.to_dict()), 200

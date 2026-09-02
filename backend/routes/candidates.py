import io
import os
import zipfile

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from dateutils import parse_datetime
from file_storage import candidate_file_path, delete_candidate_file, delete_candidate_files, save_candidate_file
from validation import validate_choice
from models import (
    CandidateDocument,
    CandidateScreeningAnswer,
    CandidateStageProgress,
    Candidate,
    Job,
    OnboardingDocumentItem,
    ScreeningQuestion,
    MeetingStageTemplate,
    db,
    is_email_blocked,
)

candidates_bp = Blueprint('candidates', __name__)

# Interview recordings (see upload_recording/download_recording below) -
# whatever a recruiter's meeting software (RingCentral, etc.) exports.
# Recruiter-authenticated only (unlike routes/status.py's public upload),
# so this skips that route's magic-byte content sniffing - extension +
# size is enough of a bar for an internal, already-logged-in user.
ALLOWED_RECORDING_EXTENSIONS = {'.mp4', '.mov', '.webm', '.m4v'}
MAX_RECORDING_SIZE_BYTES = 500 * 1024 * 1024  # 500MB - see config.py's MAX_CONTENT_LENGTH,
# which must be at least this large or Flask rejects the upload before this
# route ever sees it.

# Resumes and onboarding documents are much smaller than that, and need
# their own explicit caps now that MAX_CONTENT_LENGTH is sized for
# recordings instead - it's too high a ceiling to rely on alone for these
# (see routes/apply.py's identical MAX_RESUME_SIZE_BYTES, for the public
# apply-form equivalent of upload_resume below, and routes/status.py's
# MAX_UPLOAD_SIZE_BYTES for the candidate-facing equivalent of
# upload_document).
MAX_RESUME_SIZE_BYTES = 15 * 1024 * 1024  # 15MB
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10MB


def _reject_if_too_large(file, max_size_bytes):
    """Returns a (message, 400) tuple if `file` exceeds max_size_bytes, else
    None. Shared by upload_resume/upload_document/upload_recording below -
    each just supplies its own cap."""
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        return jsonify({"error": f"that file is too large - please upload something under {max_mb}MB"}), 400
    return None


@candidates_bp.route('/api/candidates', methods=['GET'])
@jwt_required()
def get_candidates():
    query = Candidate.query

    search = request.args.get('search')
    if search:
        query = query.filter(
            (Candidate.name.ilike(f'%{search}%')) |
            (Candidate.email.ilike(f'%{search}%'))
        )

    stage = request.args.get('stage')
    if stage:
        query = query.filter_by(stage=stage)

    job_id = request.args.get('job_id')
    if job_id:
        query = query.filter_by(job_id=job_id)

    candidates = query.all()
    return jsonify([c.to_dict() for c in candidates]), 200


@candidates_bp.route('/api/candidates/<int:candidate_id>', methods=['GET'])
@jwt_required()
def get_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    return jsonify(candidate.to_detail_dict()), 200


@candidates_bp.route('/api/candidates', methods=['POST'])
@jwt_required()
def create_candidate():
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    email = data.get('email')
    if not name or not email:
        return jsonify({"error": "name and email are required"}), 400

    job_id = data.get('job_id')
    if job_id is not None and not Job.query.get(job_id):
        return jsonify({"error": f"no job with id {job_id}"}), 400

    stage = data.get('stage', 'Applied')
    error = validate_choice({'stage': stage}, 'stage', Candidate.VALID_STAGES)
    if error:
        return jsonify({"error": error}), 400
    if is_email_blocked(email):
        return jsonify({"error": "this email is on the blocklist"}), 403

    candidate = Candidate(
        name=name,
        email=email,
        phone=data.get('phone'),
        job_id=job_id,
        stage=stage,
        status=data.get('status', 'Active'),
        interviewer=data.get('interviewer'),
        scheduled=data.get('scheduled', False),
        city=data.get('city'),
        state=data.get('state'),
        address_line1=data.get('address_line1'),
        postal_code=data.get('postal_code'),
        source=data.get('source'),
        work_authorized=data.get('work_authorized'),
        requires_visa_sponsorship=data.get('requires_visa_sponsorship'),
    )
    db.session.add(candidate)
    db.session.commit()
    return jsonify(candidate.to_dict()), 201


@candidates_bp.route('/api/candidates/<int:candidate_id>', methods=['PATCH'])
@jwt_required()
def update_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    data = request.get_json(silent=True) or {}

    error = validate_choice(data, 'stage', Candidate.VALID_STAGES)
    if error:
        return jsonify({"error": error}), 400

    if 'job_id' in data and data['job_id'] is not None and not Job.query.get(data['job_id']):
        return jsonify({"error": f"no job with id {data['job_id']}"}), 400

    for field in (
        'name', 'email', 'phone', 'job_id', 'stage', 'status', 'interviewer', 'scheduled',
        'city', 'state', 'address_line1', 'postal_code', 'source',
        'work_authorized', 'requires_visa_sponsorship',
    ):
        if field in data:
            setattr(candidate, field, data[field])

    db.session.commit()
    return jsonify(candidate.to_detail_dict()), 200


@candidates_bp.route('/api/candidates/<int:candidate_id>', methods=['DELETE'])
@jwt_required()
def delete_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    db.session.delete(candidate)
    db.session.commit()
    delete_candidate_files(candidate_id)
    return '', 204


# --- Resume -----------------------------------------------------------------

@candidates_bp.route('/api/candidates/<int:candidate_id>/resume', methods=['POST'])
@jwt_required()
def upload_resume(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"error": "file is required"}), 400
    too_large = _reject_if_too_large(file, MAX_RESUME_SIZE_BYTES)
    if too_large:
        return too_large

    if candidate.resume_stored_filename:
        delete_candidate_file(candidate.id, candidate.resume_stored_filename)

    original_filename, stored_filename = save_candidate_file(candidate.id, file)
    candidate.resume_original_filename = original_filename
    candidate.resume_stored_filename = stored_filename
    db.session.commit()
    return jsonify(candidate.to_detail_dict()), 200


@candidates_bp.route('/api/candidates/<int:candidate_id>/resume', methods=['GET'])
@jwt_required()
def download_resume(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    if not candidate.resume_stored_filename:
        return jsonify({"error": "no resume uploaded"}), 404
    return send_file(
        candidate_file_path(candidate.id, candidate.resume_stored_filename),
        download_name=candidate.resume_original_filename,
    )


# --- Onboarding documents -----------------------------------------------------

@candidates_bp.route('/api/candidates/<int:candidate_id>/documents', methods=['GET'])
@jwt_required()
def list_document_types(candidate_id):
    """The onboarding checklist for this candidate's job — every onboarding
    item across all of the job's stages (see Job.onboarding_items), each
    entry annotated with whatever the candidate has uploaded for it (if
    anything). Empty if the candidate has no job, or the job's stages define
    no onboarding items - the frontend hides the whole section in that case."""
    candidate = Candidate.query.get_or_404(candidate_id)
    uploaded = {d.onboarding_item_id: d.to_dict() for d in candidate.documents}
    items = candidate.job.onboarding_items if candidate.job else []
    return jsonify(
        [
            {
                "item_id": item.id,
                "description": item.description,
                "type": item.item_type,
                "required": item.required,
                "submission": uploaded.get(item.id),
            }
            for item in items
        ]
    ), 200


@candidates_bp.route('/api/candidates/<int:candidate_id>/documents/<int:item_id>', methods=['POST'])
@jwt_required()
def upload_document(candidate_id, item_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    item = OnboardingDocumentItem.query.get_or_404(item_id)
    if not candidate.job or item.meeting_stage_template.job_id != candidate.job_id:
        return jsonify({"error": "onboarding item does not belong to this candidate's job"}), 400

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"error": "file is required"}), 400
    too_large = _reject_if_too_large(file, MAX_DOCUMENT_SIZE_BYTES)
    if too_large:
        return too_large

    existing = CandidateDocument.query.filter_by(
        candidate_id=candidate.id, onboarding_item_id=item.id
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


@candidates_bp.route('/api/candidates/<int:candidate_id>/documents/<int:item_id>', methods=['GET'])
@jwt_required()
def download_document(candidate_id, item_id):
    document = CandidateDocument.query.filter_by(
        candidate_id=candidate_id, onboarding_item_id=item_id
    ).first_or_404()
    return send_file(
        candidate_file_path(candidate_id, document.stored_filename),
        download_name=document.original_filename,
    )


@candidates_bp.route('/api/candidates/<int:candidate_id>/documents/download-all', methods=['GET'])
@jwt_required()
def download_all_documents(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    if not candidate.documents:
        return jsonify({"error": "no documents uploaded"}), 404

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for document in candidate.documents:
            zf.write(
                candidate_file_path(candidate.id, document.stored_filename),
                arcname=document.original_filename,
            )
    buffer.seek(0)
    return send_file(buffer, download_name=f'{candidate.display_name} - documents.zip', as_attachment=True)


# --- Pre-screening answers ----------------------------------------------------

@candidates_bp.route('/api/candidates/<int:candidate_id>/screening-answers', methods=['PUT'])
@jwt_required()
def update_screening_answers(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    data = request.get_json(silent=True) or {}
    answers = data.get('answers')
    if not isinstance(answers, list):
        return jsonify({"error": "answers must be a list of {question_id, answer_text}"}), 400

    existing = {a.question_id: a for a in candidate.screening_answers}
    for entry in answers:
        question_id = entry.get('question_id')
        question = ScreeningQuestion.query.get(question_id)
        if not question or question.meeting_stage_template.job_id != candidate.job_id:
            return jsonify({"error": f"question {question_id} does not belong to this candidate's job"}), 400

        if question_id in existing:
            existing[question_id].answer_text = entry.get('answer_text')
        else:
            db.session.add(
                CandidateScreeningAnswer(
                    candidate_id=candidate.id,
                    question_id=question_id,
                    answer_text=entry.get('answer_text'),
                )
            )

    db.session.commit()
    return jsonify(candidate.to_detail_dict()), 200


# --- Stage progress (scheduling + scorecard) ----------------------------------

@candidates_bp.route(
    '/api/candidates/<int:candidate_id>/stages/<int:template_id>', methods=['PUT']
)
@jwt_required()
def update_stage_progress(candidate_id, template_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    template = MeetingStageTemplate.query.get_or_404(template_id)
    if candidate.job_id != template.job_id:
        return jsonify({"error": "meeting stage does not belong to this candidate's job"}), 400

    data = request.get_json(silent=True) or {}
    error = validate_choice(data, 'status', CandidateStageProgress.VALID_STATUSES)
    if error:
        return jsonify({"error": error}), 400

    progress = CandidateStageProgress.query.filter_by(
        candidate_id=candidate.id, meeting_stage_template_id=template.id
    ).first()
    if not progress:
        progress = CandidateStageProgress(candidate_id=candidate.id, meeting_stage_template_id=template.id)
        db.session.add(progress)

    if 'status' in data:
        progress.status = data['status']
    if 'scheduled_at' in data:
        raw = data['scheduled_at']
        if raw:
            try:
                progress.scheduled_at = parse_datetime(raw, 'scheduled_at')
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
        else:
            progress.scheduled_at = None
    if 'location' in data:
        progress.location = data['location']
    if 'notes' in data:
        progress.notes = data['notes']
    if 'cancellation_reason' in data:
        progress.cancellation_reason = data['cancellation_reason']
    if 'prompt_reschedule' in data:
        progress.prompt_reschedule = data['prompt_reschedule']
    for score_field in ('score_communication', 'score_energy', 'score_relevant_experience'):
        if score_field in data:
            value = data[score_field]
            if value is not None and value != '' and not (1 <= int(value) <= 5):
                return jsonify({"error": f"{score_field} must be between 1 and 5"}), 400
            setattr(progress, score_field, value if value not in (None, '') else None)

    db.session.commit()
    return jsonify(candidate.to_detail_dict()), 200


# --- Interview recording -------------------------------------------------------

@candidates_bp.route(
    '/api/candidates/<int:candidate_id>/stages/<int:template_id>/recording', methods=['POST']
)
@jwt_required()
def upload_recording(candidate_id, template_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    template = MeetingStageTemplate.query.get_or_404(template_id)
    if candidate.job_id != template.job_id:
        return jsonify({"error": "meeting stage does not belong to this candidate's job"}), 400

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"error": "file is required"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_RECORDING_EXTENSIONS:
        return jsonify({"error": "only MP4, MOV, WEBM, and M4V files are accepted"}), 400
    too_large = _reject_if_too_large(file, MAX_RECORDING_SIZE_BYTES)
    if too_large:
        return too_large

    progress = CandidateStageProgress.query.filter_by(
        candidate_id=candidate.id, meeting_stage_template_id=template.id
    ).first()
    if not progress:
        progress = CandidateStageProgress(candidate_id=candidate.id, meeting_stage_template_id=template.id)
        db.session.add(progress)

    if progress.recording_stored_filename:
        delete_candidate_file(candidate.id, progress.recording_stored_filename)

    original_filename, stored_filename = save_candidate_file(candidate.id, file)
    progress.recording_original_filename = original_filename
    progress.recording_stored_filename = stored_filename
    db.session.commit()
    return jsonify(candidate.to_detail_dict()), 200


@candidates_bp.route(
    '/api/candidates/<int:candidate_id>/stages/<int:template_id>/recording', methods=['GET']
)
@jwt_required(locations=['headers', 'query_string'])
def download_recording(candidate_id, template_id):
    """Locations includes query_string (like calendar_auth.py's
    microsoft_connect) since this is loaded as a plain <video src="...">, not
    fetched via JS - there's no way to attach an Authorization header to
    that, so the frontend passes the token as ?jwt=... instead (see
    api.recordingUrl). send_file's default conditional=True serves Range
    requests, which is what lets the browser seek within the video without
    downloading the whole file first."""
    progress = CandidateStageProgress.query.filter_by(
        candidate_id=candidate_id, meeting_stage_template_id=template_id
    ).first()
    if not progress or not progress.recording_stored_filename:
        return jsonify({"error": "no recording uploaded"}), 404
    return send_file(candidate_file_path(candidate_id, progress.recording_stored_filename))


@candidates_bp.route(
    '/api/candidates/<int:candidate_id>/stages/<int:template_id>/recording', methods=['DELETE']
)
@jwt_required()
def delete_recording(candidate_id, template_id):
    progress = CandidateStageProgress.query.filter_by(
        candidate_id=candidate_id, meeting_stage_template_id=template_id
    ).first()
    if not progress or not progress.recording_stored_filename:
        return jsonify({"error": "no recording uploaded"}), 404

    delete_candidate_file(candidate_id, progress.recording_stored_filename)
    progress.recording_original_filename = None
    progress.recording_stored_filename = None
    db.session.commit()
    return jsonify(Candidate.query.get(candidate_id).to_detail_dict()), 200

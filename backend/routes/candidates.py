import io
import zipfile

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from dateutils import parse_datetime
from file_storage import candidate_file_path, delete_candidate_file, delete_candidate_files, save_candidate_file
from validation import validate_choice
from models import (
    CANDIDATE_DOCUMENT_TYPES,
    CandidateDocument,
    CandidateScreeningAnswer,
    CandidateStageProgress,
    Candidate,
    Job,
    ScreeningQuestion,
    MeetingStageTemplate,
    db,
)

candidates_bp = Blueprint('candidates', __name__)

DOC_TYPE_KEYS = {doc_type for doc_type, _label in CANDIDATE_DOCUMENT_TYPES}


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
        source=data.get('source'),
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

    # Once a candidate is linked to their own account, name/email/phone are
    # read live from it (see Candidate.display_name etc. in models.py) — a
    # recruiter PATCHing these here would otherwise appear to succeed but
    # have no visible effect, which is worse than just saying no.
    if candidate.candidate_account_id is not None and any(f in data for f in ('name', 'email', 'phone')):
        return jsonify({
            "error": "this candidate's name/email/phone are managed by their own account and can't be edited here"
        }), 400

    for field in (
        'name', 'email', 'phone', 'job_id', 'stage', 'status', 'interviewer', 'scheduled',
        'city', 'state', 'source',
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
    """The fixed onboarding checklist, each entry annotated with whatever the
    candidate has uploaded for it (if anything)."""
    candidate = Candidate.query.get_or_404(candidate_id)
    uploaded = {d.doc_type: d.to_dict() for d in candidate.documents}
    return jsonify(
        [
            {"doc_type": doc_type, "label": label, "submission": uploaded.get(doc_type)}
            for doc_type, label in CANDIDATE_DOCUMENT_TYPES
        ]
    ), 200


@candidates_bp.route('/api/candidates/<int:candidate_id>/documents/<doc_type>', methods=['POST'])
@jwt_required()
def upload_document(candidate_id, doc_type):
    candidate = Candidate.query.get_or_404(candidate_id)
    if doc_type not in DOC_TYPE_KEYS:
        return jsonify({"error": f"doc_type must be one of {sorted(DOC_TYPE_KEYS)}"}), 400

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"error": "file is required"}), 400

    existing = CandidateDocument.query.filter_by(candidate_id=candidate.id, doc_type=doc_type).first()
    original_filename, stored_filename = save_candidate_file(candidate.id, file)

    if existing:
        delete_candidate_file(candidate.id, existing.stored_filename)
        existing.original_filename = original_filename
        existing.stored_filename = stored_filename
        document = existing
    else:
        document = CandidateDocument(
            candidate_id=candidate.id,
            doc_type=doc_type,
            original_filename=original_filename,
            stored_filename=stored_filename,
        )
        db.session.add(document)

    db.session.commit()
    return jsonify(document.to_dict()), 200


@candidates_bp.route('/api/candidates/<int:candidate_id>/documents/<doc_type>', methods=['GET'])
@jwt_required()
def download_document(candidate_id, doc_type):
    document = CandidateDocument.query.filter_by(candidate_id=candidate_id, doc_type=doc_type).first_or_404()
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
    for score_field in ('score_communication', 'score_energy', 'score_relevant_experience'):
        if score_field in data:
            value = data[score_field]
            if value is not None and value != '' and not (1 <= int(value) <= 5):
                return jsonify({"error": f"{score_field} must be between 1 and 5"}), 400
            setattr(progress, score_field, value if value not in (None, '') else None)

    db.session.commit()
    return jsonify(candidate.to_detail_dict()), 200

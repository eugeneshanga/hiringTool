from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from dateutils import parse_datetime
from models import db, Interview, Job, Candidate, MeetingStageTemplate
from validation import validate_choice

interviews_bp = Blueprint('interviews', __name__)


def _validate_meeting_stage_template(template_id, job_id):
    """Returns an error message if template_id doesn't refer to a real
    MeetingStageTemplate belonging to job_id, else None."""
    template = MeetingStageTemplate.query.get(template_id)
    if not template:
        return f"no meeting stage template with id {template_id}"
    if template.job_id != job_id:
        return "meeting_stage_template_id does not belong to job_id"
    return None


@interviews_bp.route('/api/interviews', methods=['GET'])
@jwt_required()
def get_interviews():
    query = Interview.query

    if request.args.get('upcoming') == 'true':
        query = query.filter(Interview.scheduled_start >= datetime.utcnow())

    job_id = request.args.get('job_id')
    if job_id:
        query = query.filter_by(job_id=job_id)

    interviews = query.order_by(Interview.scheduled_start.asc()).all()
    return jsonify([i.to_dict() for i in interviews]), 200


@interviews_bp.route('/api/interviews/<int:interview_id>', methods=['GET'])
@jwt_required()
def get_interview(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    return jsonify(interview.to_dict()), 200


@interviews_bp.route('/api/interviews', methods=['POST'])
@jwt_required()
def create_interview():
    data = request.get_json(silent=True) or {}

    stage_name = data.get('stage_name')
    meeting_type = data.get('meeting_type')
    if not stage_name or not meeting_type:
        return jsonify({"error": "stage_name and meeting_type are required"}), 400
    error = validate_choice(data, 'meeting_type', Interview.VALID_MEETING_TYPES)
    if error:
        return jsonify({"error": error}), 400

    try:
        start = parse_datetime(data.get('scheduled_start'), 'scheduled_start')
        end = parse_datetime(data.get('scheduled_end'), 'scheduled_end')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    if end <= start:
        return jsonify({"error": "scheduled_end must be after scheduled_start"}), 400

    job_id = data.get('job_id')
    if job_id is not None and not Job.query.get(job_id):
        return jsonify({"error": f"no job with id {job_id}"}), 400

    meeting_stage_template_id = data.get('meeting_stage_template_id')
    if meeting_stage_template_id is not None:
        err = _validate_meeting_stage_template(meeting_stage_template_id, job_id)
        if err:
            return jsonify({"error": err}), 400

    capacity = data.get('capacity', 1)
    if not isinstance(capacity, int) or capacity < 1:
        return jsonify({"error": "capacity must be a positive integer"}), 400

    interview = Interview(
        job_id=job_id,
        meeting_stage_template_id=meeting_stage_template_id,
        stage_name=stage_name,
        meeting_type=meeting_type,
        location=data.get('location'),
        scheduled_start=start,
        scheduled_end=end,
        capacity=capacity,
    )
    db.session.add(interview)
    db.session.commit()
    return jsonify(interview.to_dict()), 201


@interviews_bp.route('/api/interviews/<int:interview_id>', methods=['PATCH'])
@jwt_required()
def update_interview(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    data = request.get_json(silent=True) or {}

    if 'scheduled_start' in data:
        try:
            interview.scheduled_start = parse_datetime(data['scheduled_start'], 'scheduled_start')
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    if 'scheduled_end' in data:
        try:
            interview.scheduled_end = parse_datetime(data['scheduled_end'], 'scheduled_end')
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    if interview.scheduled_end <= interview.scheduled_start:
        return jsonify({"error": "scheduled_end must be after scheduled_start"}), 400

    if 'job_id' in data and data['job_id'] is not None and not Job.query.get(data['job_id']):
        return jsonify({"error": f"no job with id {data['job_id']}"}), 400

    error = validate_choice(data, 'meeting_type', Interview.VALID_MEETING_TYPES)
    if error:
        return jsonify({"error": error}), 400

    if 'meeting_stage_template_id' in data and data['meeting_stage_template_id'] is not None:
        effective_job_id = data.get('job_id', interview.job_id)
        err = _validate_meeting_stage_template(data['meeting_stage_template_id'], effective_job_id)
        if err:
            return jsonify({"error": err}), 400

    if 'capacity' in data:
        capacity = data['capacity']
        if not isinstance(capacity, int) or capacity < 1:
            return jsonify({"error": "capacity must be a positive integer"}), 400
        if capacity < len(interview.candidates):
            return jsonify({"error": "capacity cannot be lower than the number of already-enrolled candidates"}), 400

    for field in ('job_id', 'meeting_stage_template_id', 'stage_name', 'meeting_type', 'location', 'capacity'):
        if field in data:
            setattr(interview, field, data[field])

    db.session.commit()
    return jsonify(interview.to_dict()), 200


@interviews_bp.route('/api/interviews/<int:interview_id>', methods=['DELETE'])
@jwt_required()
def delete_interview(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    db.session.delete(interview)
    db.session.commit()
    return '', 204


@interviews_bp.route('/api/interviews/<int:interview_id>/enroll', methods=['POST'])
@jwt_required()
def enroll_candidate(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    data = request.get_json(silent=True) or {}
    candidate_id = data.get('candidate_id')

    candidate = Candidate.query.get(candidate_id) if candidate_id else None
    if not candidate:
        return jsonify({"error": f"no candidate with id {candidate_id}"}), 400

    if candidate in interview.candidates:
        return jsonify({"error": f"{candidate.name} is already enrolled in this interview"}), 400

    if len(interview.candidates) >= interview.capacity:
        return jsonify({"error": "this interview is already at capacity"}), 400

    interview.candidates.append(candidate)
    # Enrolling in any interview session moves the candidate into the Interview
    # stage of the pipeline. This always overwrites their current stage - manual
    # stage changes on the Candidates page remain available as an override.
    candidate.stage = 'Interview'
    db.session.commit()
    return jsonify(interview.to_dict()), 200


@interviews_bp.route('/api/interviews/<int:interview_id>/unenroll', methods=['POST'])
@jwt_required()
def unenroll_candidate(interview_id):
    interview = Interview.query.get_or_404(interview_id)
    data = request.get_json(silent=True) or {}
    candidate_id = data.get('candidate_id')

    candidate = Candidate.query.get(candidate_id) if candidate_id else None
    if not candidate or candidate not in interview.candidates:
        return jsonify({"error": "candidate is not enrolled in this interview"}), 400

    interview.candidates.remove(candidate)
    db.session.commit()
    return jsonify(interview.to_dict()), 200

from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, Interview, Job, Candidate

interviews_bp = Blueprint('interviews', __name__)


def parse_datetime(value, field_name):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an ISO-8601 datetime string")


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

    capacity = data.get('capacity', 1)
    if not isinstance(capacity, int) or capacity < 1:
        return jsonify({"error": "capacity must be a positive integer"}), 400

    interview = Interview(
        job_id=job_id,
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

    if 'capacity' in data:
        capacity = data['capacity']
        if not isinstance(capacity, int) or capacity < 1:
            return jsonify({"error": "capacity must be a positive integer"}), 400
        if capacity < len(interview.candidates):
            return jsonify({"error": "capacity cannot be lower than the number of already-enrolled candidates"}), 400

    for field in ('job_id', 'stage_name', 'meeting_type', 'location', 'capacity'):
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

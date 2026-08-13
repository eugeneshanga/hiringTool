from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, Candidate, Job

candidates_bp = Blueprint('candidates', __name__)


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
    return jsonify(candidate.to_dict()), 200


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
    if stage not in Candidate.VALID_STAGES:
        return jsonify({"error": f"stage must be one of {Candidate.VALID_STAGES}"}), 400

    candidate = Candidate(
        name=name,
        email=email,
        phone=data.get('phone'),
        job_id=job_id,
        stage=stage,
        status=data.get('status', 'Active'),
        interviewer=data.get('interviewer'),
        scheduled=data.get('scheduled', False),
    )
    db.session.add(candidate)
    db.session.commit()
    return jsonify(candidate.to_dict()), 201


@candidates_bp.route('/api/candidates/<int:candidate_id>', methods=['PATCH'])
@jwt_required()
def update_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    data = request.get_json(silent=True) or {}

    if 'stage' in data and data['stage'] not in Candidate.VALID_STAGES:
        return jsonify({"error": f"stage must be one of {Candidate.VALID_STAGES}"}), 400

    if 'job_id' in data and data['job_id'] is not None and not Job.query.get(data['job_id']):
        return jsonify({"error": f"no job with id {data['job_id']}"}), 400

    for field in ('name', 'email', 'phone', 'job_id', 'stage', 'status', 'interviewer', 'scheduled'):
        if field in data:
            setattr(candidate, field, data[field])

    db.session.commit()
    return jsonify(candidate.to_dict()), 200


@candidates_bp.route('/api/candidates/<int:candidate_id>', methods=['DELETE'])
@jwt_required()
def delete_candidate(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)
    db.session.delete(candidate)
    db.session.commit()
    return '', 204

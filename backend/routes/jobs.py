from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, Job

jobs_bp = Blueprint('jobs', __name__)

VALID_STATUSES = ('Open', 'Closed', 'Draft')


@jobs_bp.route('/api/jobs', methods=['GET'])
@jwt_required()
def get_jobs():
    query = Job.query

    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    jobs = query.order_by(Job.created_at.desc()).all()
    return jsonify([j.to_dict() for j in jobs]), 200


@jobs_bp.route('/api/jobs/<int:job_id>', methods=['GET'])
@jwt_required()
def get_job(job_id):
    job = Job.query.get_or_404(job_id)
    return jsonify(job.to_dict()), 200


@jobs_bp.route('/api/jobs', methods=['POST'])
@jwt_required()
def create_job():
    data = request.get_json(silent=True) or {}
    title = data.get('title')
    if not title:
        return jsonify({"error": "title is required"}), 400

    status = data.get('status', 'Open')
    if status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {VALID_STATUSES}"}), 400

    job = Job(
        title=title,
        department=data.get('department'),
        location=data.get('location'),
        status=status,
        description=data.get('description'),
    )
    db.session.add(job)
    db.session.commit()
    return jsonify(job.to_dict()), 201


@jobs_bp.route('/api/jobs/<int:job_id>', methods=['PATCH'])
@jwt_required()
def update_job(job_id):
    job = Job.query.get_or_404(job_id)
    data = request.get_json(silent=True) or {}

    if 'status' in data and data['status'] not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {VALID_STATUSES}"}), 400

    for field in ('title', 'department', 'location', 'status', 'description'):
        if field in data:
            setattr(job, field, data[field])

    db.session.commit()
    return jsonify(job.to_dict()), 200


@jobs_bp.route('/api/jobs/<int:job_id>', methods=['DELETE'])
@jwt_required()
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    db.session.delete(job)
    db.session.commit()
    return '', 204

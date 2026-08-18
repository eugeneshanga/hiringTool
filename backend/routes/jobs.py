from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, Job
from validation import validate_choice

jobs_bp = Blueprint('jobs', __name__)


def validate_job_fields(data, partial=False):
    """Returns an error message string, or None if the payload is valid."""
    error = validate_choice(data, 'status', Job.VALID_STATUSES) or validate_choice(
        data, 'salary_period', Job.VALID_SALARY_PERIODS
    )
    if error:
        return error

    if 'job_type' in data:
        job_type = data['job_type']
        if not isinstance(job_type, list) or any(t not in Job.VALID_JOB_TYPES for t in job_type):
            return f"job_type must be a list of values from {Job.VALID_JOB_TYPES}"

    min_salary = data.get('min_salary')
    max_salary = data.get('max_salary')
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        return "min_salary cannot be greater than max_salary"

    if 'highlights' in data and not isinstance(data['highlights'], list):
        return "highlights must be a list of strings"

    return None


@jobs_bp.route('/api/jobs', methods=['GET'])
@jwt_required()
def get_jobs():
    query = Job.query

    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)

    search = request.args.get('search')
    if search:
        query = query.filter(Job.title.ilike(f'%{search}%'))

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

    error = validate_job_fields(data)
    if error:
        return jsonify({"error": error}), 400

    job = Job(
        title=title,
        status=data.get('status', 'Draft'),
        job_type=data.get('job_type', []),
        city=data.get('city'),
        state=data.get('state'),
        postal_code=data.get('postal_code'),
        country=data.get('country', 'USA'),
        min_salary=data.get('min_salary'),
        max_salary=data.get('max_salary'),
        salary_period=data.get('salary_period'),
        highlights=data.get('highlights', []),
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

    error = validate_job_fields(data, partial=True)
    if error:
        return jsonify({"error": error}), 400

    for field in (
        'title', 'status', 'job_type', 'city', 'state', 'postal_code', 'country',
        'min_salary', 'max_salary', 'salary_period', 'highlights', 'description',
    ):
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

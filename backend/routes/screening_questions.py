from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, Job, JobScreeningQuestion

screening_questions_bp = Blueprint('screening_questions', __name__)


@screening_questions_bp.route('/api/jobs/<int:job_id>/screening-questions', methods=['GET'])
@jwt_required()
def list_screening_questions(job_id):
    Job.query.get_or_404(job_id)
    questions = (
        JobScreeningQuestion.query.filter_by(job_id=job_id)
        .order_by(JobScreeningQuestion.sort_order.asc(), JobScreeningQuestion.id.asc())
        .all()
    )
    return jsonify([q.to_dict() for q in questions]), 200


@screening_questions_bp.route('/api/jobs/<int:job_id>/screening-questions', methods=['POST'])
@jwt_required()
def create_screening_question(job_id):
    Job.query.get_or_404(job_id)
    data = request.get_json(silent=True) or {}
    question_text = (data.get('question_text') or '').strip()
    if not question_text:
        return jsonify({"error": "question_text is required"}), 400

    max_order = (
        db.session.query(db.func.max(JobScreeningQuestion.sort_order))
        .filter_by(job_id=job_id)
        .scalar()
    )
    question = JobScreeningQuestion(
        job_id=job_id,
        question_text=question_text,
        sort_order=(max_order + 1) if max_order is not None else 0,
    )
    db.session.add(question)
    db.session.commit()
    return jsonify(question.to_dict()), 201


@screening_questions_bp.route(
    '/api/jobs/<int:job_id>/screening-questions/<int:question_id>', methods=['DELETE']
)
@jwt_required()
def delete_screening_question(job_id, question_id):
    question = JobScreeningQuestion.query.filter_by(id=question_id, job_id=job_id).first_or_404()
    db.session.delete(question)
    db.session.commit()
    return '', 204

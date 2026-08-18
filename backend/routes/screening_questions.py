from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, MeetingStageTemplate, ScreeningQuestion

screening_questions_bp = Blueprint('screening_questions', __name__)


def _get_template(job_id, template_id):
    return MeetingStageTemplate.query.filter_by(id=template_id, job_id=job_id).first_or_404()


def _parse_question_fields(data, existing_answer_options=None):
    """Validates question_text/question_label/answer_options/qualified_answers
    from a request payload. Returns (fields, error) — fields is a dict ready
    to apply via setattr, error is a message string (or None on success).
    existing_answer_options lets an update request send only qualified_answers
    without re-sending answer_options."""
    fields = {}

    question_text = (data.get('question_text') or '').strip()
    if not question_text:
        return None, "question_text is required"
    fields['question_text'] = question_text

    if 'question_label' in data:
        label = (data.get('question_label') or '').strip()
        fields['question_label'] = label or None

    if 'answer_options' in data:
        raw_options = data['answer_options']
        if not isinstance(raw_options, list) or not all(isinstance(o, str) for o in raw_options):
            return None, "answer_options must be a list of strings"
        answer_options = [o.strip() for o in raw_options if o.strip()]
        fields['answer_options'] = answer_options
    else:
        answer_options = existing_answer_options or []

    if 'qualified_answers' in data:
        raw_qualified = data['qualified_answers']
        if not isinstance(raw_qualified, list) or not all(isinstance(o, str) for o in raw_qualified):
            return None, "qualified_answers must be a list of strings"
        if not set(raw_qualified).issubset(set(answer_options)):
            return None, "qualified_answers must be a subset of answer_options"
        fields['qualified_answers'] = raw_qualified

    return fields, None


@screening_questions_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/screening-questions', methods=['GET']
)
@jwt_required()
def list_screening_questions(job_id, template_id):
    _get_template(job_id, template_id)
    questions = (
        ScreeningQuestion.query.filter_by(meeting_stage_template_id=template_id)
        .order_by(ScreeningQuestion.sort_order.asc(), ScreeningQuestion.id.asc())
        .all()
    )
    return jsonify([q.to_dict() for q in questions]), 200


@screening_questions_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/screening-questions', methods=['POST']
)
@jwt_required()
def create_screening_question(job_id, template_id):
    _get_template(job_id, template_id)
    data = request.get_json(silent=True) or {}

    fields, error = _parse_question_fields(data)
    if error:
        return jsonify({"error": error}), 400

    max_order = (
        db.session.query(db.func.max(ScreeningQuestion.sort_order))
        .filter_by(meeting_stage_template_id=template_id)
        .scalar()
    )
    question = ScreeningQuestion(
        meeting_stage_template_id=template_id,
        sort_order=(max_order + 1) if max_order is not None else 0,
        **fields,
    )
    db.session.add(question)
    db.session.commit()
    return jsonify(question.to_dict()), 201


@screening_questions_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/screening-questions/<int:question_id>',
    methods=['PATCH'],
)
@jwt_required()
def update_screening_question(job_id, template_id, question_id):
    _get_template(job_id, template_id)
    question = ScreeningQuestion.query.filter_by(
        id=question_id, meeting_stage_template_id=template_id
    ).first_or_404()
    data = request.get_json(silent=True) or {}

    fields, error = _parse_question_fields(data, existing_answer_options=question.answer_options)
    if error:
        return jsonify({"error": error}), 400

    for key, value in fields.items():
        setattr(question, key, value)
    db.session.commit()
    return jsonify(question.to_dict()), 200


@screening_questions_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/screening-questions/<int:question_id>',
    methods=['DELETE'],
)
@jwt_required()
def delete_screening_question(job_id, template_id, question_id):
    _get_template(job_id, template_id)
    question = ScreeningQuestion.query.filter_by(
        id=question_id, meeting_stage_template_id=template_id
    ).first_or_404()
    db.session.delete(question)
    db.session.commit()
    return '', 204

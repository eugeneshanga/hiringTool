from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, MeetingStageTemplate, OnboardingDocumentItem

onboarding_items_bp = Blueprint('onboarding_items', __name__)


def _get_template(job_id, template_id):
    return MeetingStageTemplate.query.filter_by(id=template_id, job_id=job_id).first_or_404()


def _parse_item_fields(data):
    """Validates description/type/required from a request payload. Returns
    (fields, error) — fields is a dict ready to apply via setattr, error is a
    message string (or None on success)."""
    fields = {}

    description = (data.get('description') or '').strip()
    if not description:
        return None, "description is required"
    fields['description'] = description

    if 'type' in data:
        item_type = data['type']
        if item_type not in OnboardingDocumentItem.VALID_TYPES:
            return None, f"type must be one of {list(OnboardingDocumentItem.VALID_TYPES)}"
        fields['item_type'] = item_type

    if 'required' in data:
        if not isinstance(data['required'], bool):
            return None, "required must be a boolean"
        fields['required'] = data['required']

    return fields, None


@onboarding_items_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/onboarding-items', methods=['GET']
)
@jwt_required()
def list_onboarding_items(job_id, template_id):
    _get_template(job_id, template_id)
    items = (
        OnboardingDocumentItem.query.filter_by(meeting_stage_template_id=template_id)
        .order_by(OnboardingDocumentItem.sort_order.asc(), OnboardingDocumentItem.id.asc())
        .all()
    )
    return jsonify([i.to_dict() for i in items]), 200


@onboarding_items_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/onboarding-items', methods=['POST']
)
@jwt_required()
def create_onboarding_item(job_id, template_id):
    _get_template(job_id, template_id)
    data = request.get_json(silent=True) or {}

    fields, error = _parse_item_fields(data)
    if error:
        return jsonify({"error": error}), 400

    max_order = (
        db.session.query(db.func.max(OnboardingDocumentItem.sort_order))
        .filter_by(meeting_stage_template_id=template_id)
        .scalar()
    )
    item = OnboardingDocumentItem(
        meeting_stage_template_id=template_id,
        sort_order=(max_order + 1) if max_order is not None else 0,
        **fields,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@onboarding_items_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/onboarding-items/<int:item_id>',
    methods=['PATCH'],
)
@jwt_required()
def update_onboarding_item(job_id, template_id, item_id):
    _get_template(job_id, template_id)
    item = OnboardingDocumentItem.query.filter_by(
        id=item_id, meeting_stage_template_id=template_id
    ).first_or_404()
    data = request.get_json(silent=True) or {}

    fields, error = _parse_item_fields(data)
    if error:
        return jsonify({"error": error}), 400

    for key, value in fields.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify(item.to_dict()), 200


@onboarding_items_bp.route(
    '/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/onboarding-items/<int:item_id>',
    methods=['DELETE'],
)
@jwt_required()
def delete_onboarding_item(job_id, template_id, item_id):
    _get_template(job_id, template_id)
    item = OnboardingDocumentItem.query.filter_by(
        id=item_id, meeting_stage_template_id=template_id
    ).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return '', 204

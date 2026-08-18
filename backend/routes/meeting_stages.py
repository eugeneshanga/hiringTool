from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, Interview, Job, MeetingStageTemplate
from validation import validate_choice

meeting_stages_bp = Blueprint('meeting_stages', __name__)


def _ordered_templates(job_id):
    return (
        MeetingStageTemplate.query.filter_by(job_id=job_id)
        .order_by(MeetingStageTemplate.sort_order.asc(), MeetingStageTemplate.id.asc())
        .all()
    )


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages', methods=['GET'])
@jwt_required()
def get_meeting_stages(job_id):
    Job.query.get_or_404(job_id)
    templates = _ordered_templates(job_id)
    return jsonify([t.to_dict() for t in templates]), 200


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages/<int:template_id>', methods=['GET'])
@jwt_required()
def get_meeting_stage(job_id, template_id):
    template = MeetingStageTemplate.query.filter_by(id=template_id, job_id=job_id).first_or_404()
    return jsonify(template.to_dict()), 200


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages/available', methods=['GET'])
@jwt_required()
def get_available_meeting_stages(job_id):
    """Meeting stages already defined on other jobs that this job doesn't have yet,
    for the "add existing meeting stage" picker."""
    Job.query.get_or_404(job_id)
    existing = {
        (t.meeting_type, t.stage_name)
        for t in MeetingStageTemplate.query.filter_by(job_id=job_id).all()
    }

    seen = set()
    options = []
    all_templates = MeetingStageTemplate.query.order_by(
        MeetingStageTemplate.meeting_type.asc(), MeetingStageTemplate.stage_name.asc()
    ).all()
    for t in all_templates:
        key = (t.meeting_type, t.stage_name)
        if key in existing or key in seen:
            continue
        seen.add(key)
        options.append(
            {
                "meeting_type": t.meeting_type,
                "stage_name": t.stage_name,
                "duration_minutes": t.duration_minutes,
            }
        )
    return jsonify(options), 200


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages', methods=['POST'])
@jwt_required()
def create_meeting_stage(job_id):
    Job.query.get_or_404(job_id)
    data = request.get_json(silent=True) or {}

    meeting_type = data.get('meeting_type')
    stage_name = data.get('stage_name')
    duration_minutes = data.get('duration_minutes')

    if not meeting_type or not stage_name:
        return jsonify({"error": "meeting_type and stage_name are required"}), 400
    error = validate_choice(data, 'meeting_type', MeetingStageTemplate.VALID_MEETING_TYPES)
    if error:
        return jsonify({"error": error}), 400
    if duration_minutes is not None and duration_minutes != '':
        try:
            duration_minutes = int(duration_minutes)
        except (TypeError, ValueError):
            return jsonify({"error": "duration_minutes must be an integer"}), 400
    else:
        duration_minutes = None

    max_order = (
        db.session.query(db.func.max(MeetingStageTemplate.sort_order))
        .filter_by(job_id=job_id)
        .scalar()
    )
    template = MeetingStageTemplate(
        job_id=job_id,
        meeting_type=meeting_type,
        stage_name=stage_name,
        duration_minutes=duration_minutes,
        sort_order=(max_order + 1) if max_order is not None else 0,
    )
    db.session.add(template)
    db.session.commit()
    return jsonify(template.to_dict()), 201


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages/<int:template_id>', methods=['PATCH'])
@jwt_required()
def update_meeting_stage(job_id, template_id):
    template = MeetingStageTemplate.query.filter_by(id=template_id, job_id=job_id).first_or_404()
    data = request.get_json(silent=True) or {}

    error = validate_choice(data, 'meeting_type', MeetingStageTemplate.VALID_MEETING_TYPES)
    if error:
        return jsonify({"error": error}), 400
    if 'stage_name' in data and not data['stage_name']:
        return jsonify({"error": "stage_name cannot be empty"}), 400
    if 'duration_minutes' in data:
        duration_minutes = data['duration_minutes']
        if duration_minutes is not None and duration_minutes != '':
            try:
                data['duration_minutes'] = int(duration_minutes)
            except (TypeError, ValueError):
                return jsonify({"error": "duration_minutes must be an integer"}), 400
        else:
            data['duration_minutes'] = None

    old_stage_name = template.stage_name
    for field in ('meeting_type', 'stage_name', 'duration_minutes'):
        if field in data:
            setattr(template, field, data[field])

    # Interview.stage_name is a denormalized display copy, kept in sync via
    # the meeting_stage_template_id FK rather than by re-matching on the old
    # name — see code review note on the previous name-matching approach.
    if 'stage_name' in data and data['stage_name'] != old_stage_name:
        Interview.query.filter_by(meeting_stage_template_id=template.id).update(
            {'stage_name': data['stage_name']}
        )

    db.session.commit()
    return jsonify(template.to_dict()), 200


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages/<int:template_id>/move', methods=['PATCH'])
@jwt_required()
def move_meeting_stage(job_id, template_id):
    data = request.get_json(silent=True) or {}
    direction = data.get('direction')
    if direction not in ('up', 'down'):
        return jsonify({"error": "direction must be 'up' or 'down'"}), 400

    templates = _ordered_templates(job_id)
    index = next((i for i, t in enumerate(templates) if t.id == template_id), None)
    if index is None:
        return jsonify({"error": "meeting stage not found"}), 404

    swap_index = index - 1 if direction == 'up' else index + 1
    if 0 <= swap_index < len(templates):
        templates[index].sort_order, templates[swap_index].sort_order = (
            templates[swap_index].sort_order,
            templates[index].sort_order,
        )
        db.session.commit()
        templates = _ordered_templates(job_id)

    return jsonify([t.to_dict() for t in templates]), 200


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages/<int:template_id>', methods=['DELETE'])
@jwt_required()
def delete_meeting_stage(job_id, template_id):
    template = MeetingStageTemplate.query.filter_by(id=template_id, job_id=job_id).first_or_404()
    db.session.delete(template)
    db.session.commit()
    return '', 204

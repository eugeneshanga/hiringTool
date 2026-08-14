from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from models import db, Job, Interview, MeetingStageTemplate

meeting_stages_bp = Blueprint('meeting_stages', __name__)


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages', methods=['GET'])
@jwt_required()
def get_meeting_stages(job_id):
    Job.query.get_or_404(job_id)
    templates = MeetingStageTemplate.query.filter_by(job_id=job_id).order_by(MeetingStageTemplate.id.asc()).all()
    return jsonify([t.to_dict() for t in templates]), 200


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages', methods=['POST'])
@jwt_required()
def create_meeting_stage(job_id):
    Job.query.get_or_404(job_id)
    data = request.get_json(silent=True) or {}

    meeting_type = data.get('meeting_type')
    stage_name = data.get('stage_name')
    if not meeting_type or not stage_name:
        return jsonify({"error": "meeting_type and stage_name are required"}), 400
    if meeting_type not in Interview.VALID_MEETING_TYPES:
        return jsonify({"error": f"meeting_type must be one of {Interview.VALID_MEETING_TYPES}"}), 400

    template = MeetingStageTemplate(job_id=job_id, meeting_type=meeting_type, stage_name=stage_name)
    db.session.add(template)
    db.session.commit()
    return jsonify(template.to_dict()), 201


@meeting_stages_bp.route('/api/jobs/<int:job_id>/meeting-stages/<int:template_id>', methods=['DELETE'])
@jwt_required()
def delete_meeting_stage(job_id, template_id):
    template = MeetingStageTemplate.query.filter_by(id=template_id, job_id=job_id).first_or_404()
    db.session.delete(template)
    db.session.commit()
    return '', 204

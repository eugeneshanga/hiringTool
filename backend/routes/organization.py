import zoneinfo

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from auth_helpers import admin_required
from file_storage import delete_organization_file, organization_file_path, save_organization_file
from validation import validate_choice
from models import BlocklistEntry, Organization, User, db

organization_bp = Blueprint('organization', __name__)


def _get_organization():
    """Single-tenant app - there's always exactly one Organization row,
    created on first access rather than via a migration data-seed so a fresh
    clone doesn't need special-casing."""
    org = Organization.query.first()
    if not org:
        org = Organization(name='My Organization')
        db.session.add(org)
        db.session.commit()
    return org


# --- Organization (name, logo, banner) ---------------------------------------
# GET is available to any recruiter (the header's account dropdown shows the
# org name/logo to everyone) - only editing is admin-only.

@organization_bp.route('/api/organization', methods=['GET'])
@jwt_required()
def get_organization():
    return jsonify(_get_organization().to_dict()), 200


@organization_bp.route('/api/organization', methods=['PATCH'])
@admin_required
def update_organization():
    org = _get_organization()
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({"error": "name is required"}), 400
        org.name = name

    if 'scheduling_timezone' in data:
        tz_name = (data.get('scheduling_timezone') or '').strip()
        if not tz_name:
            return jsonify({"error": "timezone is required"}), 400
        try:
            zoneinfo.ZoneInfo(tz_name)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            return jsonify({"error": f"'{tz_name}' is not a recognized timezone"}), 400
        org.scheduling_timezone = tz_name

    if 'scheduling_working_hours_start' in data or 'scheduling_working_hours_end' in data:
        start = data.get('scheduling_working_hours_start', org.scheduling_working_hours_start)
        end = data.get('scheduling_working_hours_end', org.scheduling_working_hours_end)
        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError):
            return jsonify({"error": "working hours must be whole-number hours (0-23)"}), 400
        if not (0 <= start <= 23) or not (0 <= end <= 23):
            return jsonify({"error": "working hours must be between 0 and 23"}), 400
        if start >= end:
            return jsonify({"error": "earliest time must be before latest time"}), 400
        org.scheduling_working_hours_start = start
        org.scheduling_working_hours_end = end

    if 'scheduling_days' in data:
        days = data.get('scheduling_days')
        if not isinstance(days, list) or not days:
            return jsonify({"error": "select at least one day"}), 400
        try:
            days = sorted({int(d) for d in days})
        except (TypeError, ValueError):
            return jsonify({"error": "scheduling_days must be a list of integers"}), 400
        if days[0] < 0 or days[-1] > 6:
            return jsonify({"error": "scheduling_days must each be between 0 (Monday) and 6 (Sunday)"}), 400
        org.scheduling_days = days

    db.session.commit()
    return jsonify(org.to_dict()), 200


def _upload_org_image(field_prefix):
    org = _get_organization()
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({"error": "file is required"}), 400

    existing_stored = getattr(org, f'{field_prefix}_stored_filename')
    if existing_stored:
        delete_organization_file(existing_stored)

    original_filename, stored_filename = save_organization_file(file)
    setattr(org, f'{field_prefix}_original_filename', original_filename)
    setattr(org, f'{field_prefix}_stored_filename', stored_filename)
    db.session.commit()
    return jsonify(org.to_dict()), 200


def _download_org_image(field_prefix):
    org = _get_organization()
    stored = getattr(org, f'{field_prefix}_stored_filename')
    original = getattr(org, f'{field_prefix}_original_filename')
    if not stored:
        return jsonify({"error": f"no {field_prefix} uploaded"}), 404
    return send_file(organization_file_path(stored), download_name=original)


def _delete_org_image(field_prefix):
    org = _get_organization()
    stored = getattr(org, f'{field_prefix}_stored_filename')
    if stored:
        delete_organization_file(stored)
    setattr(org, f'{field_prefix}_original_filename', None)
    setattr(org, f'{field_prefix}_stored_filename', None)
    db.session.commit()
    return jsonify(org.to_dict()), 200


@organization_bp.route('/api/organization/logo', methods=['POST'])
@admin_required
def upload_logo():
    return _upload_org_image('logo')


@organization_bp.route('/api/organization/logo', methods=['GET'])
@jwt_required()
def download_logo():
    return _download_org_image('logo')


@organization_bp.route('/api/organization/logo', methods=['DELETE'])
@admin_required
def remove_logo():
    return _delete_org_image('logo')


@organization_bp.route('/api/organization/banner', methods=['POST'])
@admin_required
def upload_banner():
    return _upload_org_image('banner')


@organization_bp.route('/api/organization/banner', methods=['GET'])
@jwt_required()
def download_banner():
    return _download_org_image('banner')


@organization_bp.route('/api/organization/banner', methods=['DELETE'])
@admin_required
def remove_banner():
    return _delete_org_image('banner')


# --- Users & licenses ----------------------------------------------------------
# "Add user" / "set new password" set a password directly rather than
# emailing an invite/reset link - this app has no email-sending
# infrastructure (see StageTabs.tsx's cancel-interview modal for the same
# constraint), so there's nowhere to send a link. The admin sets the initial
# credential themselves and passes it to the new user out of band, same as
# `flask create-user`/`flask reset-password` already require today.

@organization_bp.route('/api/organization/interviewers', methods=['GET'])
@jwt_required()
def list_interviewers():
    """Every active User, id+name only - for the stage editor's "who checks
    this calendar" picker (see MeetingStageTemplate.interviewer_user_id).
    Deliberately not @admin_required like list_users below: any recruiter
    building out a job's stages needs to be able to assign an interviewer,
    and this is a much smaller contract than the full user record (no email,
    role, etc.) that route returns."""
    users = User.query.filter_by(is_active=True).order_by(User.first_name.asc(), User.last_name.asc()).all()
    return jsonify([{"id": u.id, "name": u.name} for u in users]), 200


@organization_bp.route('/api/organization/users', methods=['GET'])
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.asc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@organization_bp.route('/api/organization/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip() or None
    password = data.get('password')
    role = data.get('role', 'recruiter')

    if not first_name or not last_name or not email or not password:
        return jsonify({"error": "first_name, last_name, email, and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    error = validate_choice({'role': role}, 'role', User.VALID_ROLES)
    if error:
        return jsonify({"error": error}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "a user with that email already exists"}), 409

    user = User(first_name=first_name, last_name=last_name, email=email, phone=phone, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@organization_bp.route('/api/organization/users/<int:user_id>', methods=['PATCH'])
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}

    error = validate_choice(data, 'role', User.VALID_ROLES)
    if error:
        return jsonify({"error": error}), 400

    # Deliberately no "deactivate yourself" guard beyond this - an admin
    # locking themselves out is recoverable via `flask create-user`/direct DB
    # access, same recovery path as before this UI existed.
    if 'role' in data:
        user.role = data['role']
    if 'is_active' in data:
        user.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify(user.to_dict()), 200


@organization_bp.route('/api/organization/users/<int:user_id>/set-password', methods=['POST'])
@admin_required
def set_user_password(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    password = data.get('password')
    if not password or len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    user.set_password(password)
    db.session.commit()
    return jsonify(user.to_dict()), 200


# --- Blocklist -----------------------------------------------------------------

@organization_bp.route('/api/organization/blocklist', methods=['GET'])
@admin_required
def list_blocklist():
    entries = BlocklistEntry.query.order_by(BlocklistEntry.created_at.desc()).all()
    return jsonify([e.to_dict() for e in entries]), 200


@organization_bp.route('/api/organization/blocklist', methods=['POST'])
@admin_required
def create_blocklist_entry():
    data = request.get_json(silent=True) or {}
    entry_type = data.get('type')
    value = (data.get('value') or '').strip().lower()
    reason = (data.get('reason') or '').strip() or None

    error = validate_choice({'type': entry_type}, 'type', BlocklistEntry.VALID_TYPES)
    if error:
        return jsonify({"error": error}), 400
    if not value:
        return jsonify({"error": "value is required"}), 400
    if entry_type == 'email' and '@' not in value:
        return jsonify({"error": "value must be a valid email address"}), 400
    if entry_type == 'domain' and '@' in value:
        return jsonify({"error": "value must be a bare domain, not an email address"}), 400
    if BlocklistEntry.query.filter_by(entry_type=entry_type, value=value).first():
        return jsonify({"error": "that entry is already on the blocklist"}), 409

    entry = BlocklistEntry(entry_type=entry_type, value=value, reason=reason)
    db.session.add(entry)
    db.session.commit()
    return jsonify(entry.to_dict()), 201


@organization_bp.route('/api/organization/blocklist/<int:entry_id>', methods=['DELETE'])
@admin_required
def delete_blocklist_entry(entry_id):
    entry = BlocklistEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return '', 204

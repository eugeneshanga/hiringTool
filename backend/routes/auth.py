from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import db, User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "invalid email or password"}), 401

    if not user.is_active:
        return jsonify({"error": "this account has been deactivated"}), 401

    token = create_access_token(identity=str(user.id), additional_claims={'account_type': 'user'})
    return jsonify({"access_token": token, "user": user.to_dict()}), 200


@auth_bp.route('/api/auth/me', methods=['GET'])
@jwt_required()
def me():
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "user not found"}), 404
    return jsonify(user.to_dict()), 200


@auth_bp.route('/api/auth/me', methods=['PATCH'])
@jwt_required()
def update_me():
    """Lets the logged-in recruiter edit their own personal info (the
    Profile page). Deliberately excludes email/role/is_active - email is the
    login identity (no re-verification flow exists to change it safely), and
    role/is_active are admin-only concerns with no self-service path today."""
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "user not found"}), 404

    data = request.get_json(silent=True) or {}

    if 'first_name' in data:
        first_name = (data.get('first_name') or '').strip()
        if not first_name:
            return jsonify({"error": "first_name is required"}), 400
        user.first_name = first_name

    if 'last_name' in data:
        last_name = (data.get('last_name') or '').strip()
        if not last_name:
            return jsonify({"error": "last_name is required"}), 400
        user.last_name = last_name

    if 'phone' in data:
        user.phone = (data.get('phone') or '').strip() or None

    if 'personal_meeting_link' in data:
        link = (data.get('personal_meeting_link') or '').strip()
        if link and not (link.startswith('http://') or link.startswith('https://')):
            return jsonify({"error": "personal_meeting_link must start with http:// or https://"}), 400
        user.personal_meeting_link = link or None

    db.session.commit()
    return jsonify(user.to_dict()), 200

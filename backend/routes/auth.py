from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import User

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

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 200


@auth_bp.route('/api/auth/me', methods=['GET'])
@jwt_required()
def me():
    user = User.query.get(int(get_jwt_identity()))
    if not user:
        return jsonify({"error": "user not found"}), 404
    return jsonify(user.to_dict()), 200

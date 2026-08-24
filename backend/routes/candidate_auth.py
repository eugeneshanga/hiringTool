from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import Candidate, db, CandidateAccount, is_email_blocked

candidate_auth_bp = Blueprint('candidate_auth', __name__)


def _issue_token(account):
    # `account_type: candidate` is what app.py's token_verification_loader
    # checks to keep this identity out of recruiter-only routes (and vice
    # versa) — see the comment there for why that check exists at all, and
    # why the claim isn't just called `type` (flask-jwt-extended reserves
    # that name for "access" vs "refresh").
    return create_access_token(identity=str(account.id), additional_claims={'account_type': 'candidate'})


@candidate_auth_bp.route('/api/candidate-auth/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    phone = (data.get('phone') or '').strip() or None
    password = data.get('password')

    if not first_name or not last_name or not email or not password:
        return jsonify({"error": "first_name, last_name, email, and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    if CandidateAccount.query.filter_by(email=email).first():
        return jsonify({"error": "an account with that email already exists"}), 409
    if is_email_blocked(email):
        return jsonify({"error": "this email is not eligible to register"}), 403

    account = CandidateAccount(first_name=first_name, last_name=last_name, email=email, phone=phone)
    account.set_password(password)
    db.session.add(account)
    db.session.commit()

    # Give recruiters visibility into every self-registered candidate right
    # away, even before they've applied to a specific job — a plain,
    # unassigned (job_id=None) row on the Candidates list, same as one a
    # recruiter would add by hand. Login never touches this; only the first
    # registration creates it, so there's exactly one per account.
    db.session.add(Candidate(
        candidate_account_id=account.id,
        name=account.name,
        email=account.email,
        phone=account.phone,
    ))
    db.session.commit()

    return jsonify({"access_token": _issue_token(account), "candidate": account.to_dict()}), 201


@candidate_auth_bp.route('/api/candidate-auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    account = CandidateAccount.query.filter_by(email=email).first()
    if not account or not account.check_password(password):
        return jsonify({"error": "invalid email or password"}), 401

    if not account.is_active:
        return jsonify({"error": "this account has been deactivated"}), 401

    return jsonify({"access_token": _issue_token(account), "candidate": account.to_dict()}), 200


@candidate_auth_bp.route('/api/candidate/me', methods=['GET'])
@jwt_required()
def me():
    account = CandidateAccount.query.get(int(get_jwt_identity()))
    if not account:
        return jsonify({"error": "account not found"}), 404
    return jsonify(account.to_dict()), 200

from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from models import User


def admin_required(fn):
    """Like @jwt_required(), but also requires the logged-in User's role to
    be 'admin'. Role isn't in the JWT itself (see app.py's account_type
    claim for why - it's a different concern, recruiter vs candidate, not
    recruiter permission level), so this looks the user up each request. The
    first role-gated routes in the app - see routes/organization.py."""

    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = User.query.get(int(get_jwt_identity()))
        if not user or user.role != 'admin':
            return jsonify({"error": "admin access required"}), 403
        return fn(*args, **kwargs)

    return wrapper

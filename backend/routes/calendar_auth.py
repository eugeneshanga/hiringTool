from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, redirect, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from google_calendar import (
    build_authorization_url,
    encrypt_token,
    exchange_code_for_tokens,
    fetch_google_email,
)
from models import CalendarConnection, User, db

calendar_auth_bp = Blueprint('calendar_auth', __name__)

# How long a /connect click has to make it through Google's consent screen
# and back to /callback before its `state` is rejected as stale.
STATE_MAX_AGE_SECONDS = 600


def _state_serializer():
    # Reuses JWT_SECRET_KEY rather than adding a second secret to manage -
    # the `salt` keeps this signature namespaced away from actual JWTs signed
    # with the same key.
    return URLSafeTimedSerializer(current_app.config['JWT_SECRET_KEY'], salt='google-oauth-state')


@calendar_auth_bp.route('/api/auth/google/connect', methods=['GET'])
@jwt_required(locations=['headers', 'query_string'])
def google_connect():
    """Kicks off the OAuth flow by redirecting to Google's consent screen.

    Meant to be visited as a real top-level browser navigation (Google's own
    redirect back to /callback only works that way), not fetched via XHR -
    which means there's no Authorization header available for @jwt_required
    to read. The frontend should navigate here with the access token as a
    query param instead: `?jwt=<access_token>` (flask-jwt-extended's default
    query-string param name), e.g.
    `window.location.href = '/api/auth/google/connect?jwt=' + token`.
    """
    user_id = int(get_jwt_identity())
    state = _state_serializer().dumps({'user_id': user_id})
    return redirect(build_authorization_url(state))


@calendar_auth_bp.route('/api/auth/google/callback', methods=['GET'])
def google_callback():
    """Google redirects here after the recruiter approves or denies consent.
    No @jwt_required here - this request comes from Google's server via the
    browser, not from our own frontend, so it carries no auth header. Instead
    the `state` param (signed in google_connect above) says which User this
    connection belongs to.

    No frontend settings page exists yet, so either outcome lands back on the
    app's home page with a query param the frontend can read:
    CALENDAR_FRONTEND_REDIRECT_URL + ?calendar_connected=true, or
    + ?calendar_error=<reason>.
    """
    frontend_url = current_app.config['CALENDAR_FRONTEND_REDIRECT_URL']

    # The user clicked "Cancel" / denied access on Google's consent screen.
    google_error = request.args.get('error')
    if google_error:
        return redirect(f'{frontend_url}?calendar_error={google_error}')

    state = request.args.get('state')
    code = request.args.get('code')
    if not state or not code:
        return redirect(f'{frontend_url}?calendar_error=missing_code_or_state')

    try:
        payload = _state_serializer().loads(state, max_age=STATE_MAX_AGE_SECONDS)
    except SignatureExpired:
        return redirect(f'{frontend_url}?calendar_error=state_expired')
    except BadSignature:
        return redirect(f'{frontend_url}?calendar_error=invalid_state')

    user = User.query.get(payload['user_id'])
    if not user:
        return redirect(f'{frontend_url}?calendar_error=unknown_user')

    try:
        tokens = exchange_code_for_tokens(code)
        access_token = tokens['access_token']
        expires_in = tokens.get('expires_in', 3600)
        refresh_token = tokens.get('refresh_token')
        google_email = fetch_google_email(access_token)
    except Exception:
        current_app.logger.exception('Google Calendar OAuth exchange failed')
        return redirect(f'{frontend_url}?calendar_error=token_exchange_failed')

    connection = CalendarConnection.query.filter_by(user_id=user.id).first()
    if not connection:
        connection = CalendarConnection(user_id=user.id)
        db.session.add(connection)

    # build_authorization_url always sets prompt=consent, so Google should
    # issue a refresh_token every time - but guard anyway rather than
    # overwrite a working refresh token with nothing on the rare response
    # that omits it.
    if refresh_token:
        connection.encrypted_refresh_token = encrypt_token(refresh_token)
    elif not connection.encrypted_refresh_token:
        return redirect(f'{frontend_url}?calendar_error=no_refresh_token')

    connection.google_email = google_email or connection.google_email or ''
    connection.access_token = access_token
    connection.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
    db.session.commit()

    return redirect(f'{frontend_url}?calendar_connected=true')


@calendar_auth_bp.route('/api/auth/google/disconnect', methods=['DELETE'])
@jwt_required()
def google_disconnect():
    user_id = int(get_jwt_identity())
    connection = CalendarConnection.query.filter_by(user_id=user_id).first()
    if not connection:
        return jsonify({"error": "no calendar connection to disconnect"}), 404

    db.session.delete(connection)
    db.session.commit()
    return '', 204


@calendar_auth_bp.route('/api/auth/google/status', methods=['GET'])
@jwt_required()
def google_status():
    """Not explicitly asked for, but connect/callback happen via full-page
    redirects with no response body the frontend can read directly - it
    needs some way to ask "is my calendar connected?" on a normal page load,
    not just react to the one-time ?calendar_connected= query param."""
    user_id = int(get_jwt_identity())
    connection = CalendarConnection.query.filter_by(user_id=user_id).first()
    if not connection:
        return jsonify({"connected": False}), 200
    return jsonify({"connected": True, "google_email": connection.google_email}), 200

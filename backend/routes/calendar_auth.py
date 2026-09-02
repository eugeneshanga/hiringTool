from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, redirect, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from microsoft_calendar import (
    build_authorization_url,
    encrypt_token,
    exchange_code_for_tokens,
    fetch_microsoft_email,
)
from models import CalendarConnection, User, db

calendar_auth_bp = Blueprint('calendar_auth', __name__)

# How long a /connect click has to make it through Microsoft's consent
# screen and back to /callback before its `state` is rejected as stale.
STATE_MAX_AGE_SECONDS = 600


def _state_serializer():
    # Reuses JWT_SECRET_KEY rather than adding a second secret to manage -
    # the `salt` keeps this signature namespaced away from actual JWTs signed
    # with the same key.
    return URLSafeTimedSerializer(current_app.config['JWT_SECRET_KEY'], salt='microsoft-oauth-state')


@calendar_auth_bp.route('/api/auth/microsoft/connect', methods=['GET'])
@jwt_required(locations=['headers', 'query_string'])
def microsoft_connect():
    """Kicks off the OAuth flow by redirecting to Microsoft's consent screen.

    Meant to be visited as a real top-level browser navigation (Microsoft's
    own redirect back to /callback only works that way), not fetched via
    XHR - which means there's no Authorization header available for
    @jwt_required to read. The frontend should navigate here with the
    access token as a query param instead: `?jwt=<access_token>`
    (flask-jwt-extended's default query-string param name), e.g.
    `window.location.href = '/api/auth/microsoft/connect?jwt=' + token`.
    """
    user_id = int(get_jwt_identity())
    state = _state_serializer().dumps({'user_id': user_id})
    return redirect(build_authorization_url(state))


@calendar_auth_bp.route('/api/auth/microsoft/callback', methods=['GET'])
def microsoft_callback():
    """Microsoft redirects here after the recruiter approves or denies
    consent. No @jwt_required here - this request comes from Microsoft's
    server via the browser, not from our own frontend, so it carries no auth
    header. Instead the `state` param (signed in microsoft_connect above)
    says which User this connection belongs to.

    Either outcome lands back on the frontend's Profile page with a query
    param it can read: CALENDAR_FRONTEND_REDIRECT_URL + ?calendar_connected=true,
    or + ?calendar_error=<reason>.
    """
    frontend_url = current_app.config['CALENDAR_FRONTEND_REDIRECT_URL']

    # The user clicked "Cancel" / denied access on Microsoft's consent screen.
    microsoft_error = request.args.get('error')
    if microsoft_error:
        return redirect(f'{frontend_url}?calendar_error={microsoft_error}')

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
        account_email = fetch_microsoft_email(access_token)
    except Exception:
        current_app.logger.exception('Microsoft Calendar OAuth exchange failed')
        return redirect(f'{frontend_url}?calendar_error=token_exchange_failed')

    connection = CalendarConnection.query.filter_by(user_id=user.id).first()
    if not connection:
        connection = CalendarConnection(user_id=user.id)
        db.session.add(connection)

    # build_authorization_url always sets prompt=consent, so Microsoft
    # should issue a refresh_token every time - but guard anyway rather than
    # overwrite a working refresh token with nothing on the rare response
    # that omits it.
    if refresh_token:
        connection.encrypted_refresh_token = encrypt_token(refresh_token)
    elif not connection.encrypted_refresh_token:
        return redirect(f'{frontend_url}?calendar_error=no_refresh_token')

    connection.account_email = account_email or connection.account_email or ''
    connection.access_token = access_token
    connection.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
    db.session.commit()

    return redirect(f'{frontend_url}?calendar_connected=true')


@calendar_auth_bp.route('/api/auth/microsoft/disconnect', methods=['DELETE'])
@jwt_required()
def microsoft_disconnect():
    user_id = int(get_jwt_identity())
    connection = CalendarConnection.query.filter_by(user_id=user_id).first()
    if not connection:
        return jsonify({"error": "no calendar connection to disconnect"}), 404

    db.session.delete(connection)
    db.session.commit()
    return '', 204


@calendar_auth_bp.route('/api/auth/microsoft/status', methods=['GET'])
@jwt_required()
def microsoft_status():
    """Not explicitly asked for, but connect/callback happen via full-page
    redirects with no response body the frontend can read directly - it
    needs some way to ask "is my calendar connected?" on a normal page load,
    not just react to the one-time ?calendar_connected= query param."""
    user_id = int(get_jwt_identity())
    connection = CalendarConnection.query.filter_by(user_id=user_id).first()
    if not connection:
        return jsonify({"connected": False}), 200
    return jsonify({"connected": True, "account_email": connection.account_email}), 200

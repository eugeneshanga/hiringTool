from datetime import datetime, timedelta

import requests
from flask import Blueprint, current_app, jsonify, redirect, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ringcentral_video import (
    RingCentralTokenError,
    build_authorization_url,
    encrypt_token,
    exchange_code_for_tokens,
    fetch_ringcentral_email,
    get_valid_access_token,
)
from models import RingCentralConnection, User, db

ringcentral_auth_bp = Blueprint('ringcentral_auth', __name__)

# How long a /connect click has to make it through RingCentral's consent
# screen and back to /callback before its `state` is rejected as stale.
STATE_MAX_AGE_SECONDS = 600


def _state_serializer():
    # Reuses JWT_SECRET_KEY, same as calendar_auth.py's Microsoft
    # equivalent - the `salt` keeps this signature namespaced away from
    # both actual JWTs and the Microsoft OAuth state signed with the same key.
    return URLSafeTimedSerializer(current_app.config['JWT_SECRET_KEY'], salt='ringcentral-oauth-state')


@ringcentral_auth_bp.route('/api/auth/ringcentral/connect', methods=['GET'])
@jwt_required(locations=['headers', 'query_string'])
def ringcentral_connect():
    """Kicks off the OAuth flow by redirecting to RingCentral's consent
    screen. Same "must be a real top-level navigation, token passed as
    ?jwt=" reasoning as calendar_auth.py's microsoft_connect - see that
    route's docstring."""
    user_id = int(get_jwt_identity())
    state = _state_serializer().dumps({'user_id': user_id})
    return redirect(build_authorization_url(state))


@ringcentral_auth_bp.route('/api/auth/ringcentral/callback', methods=['GET'])
def ringcentral_callback():
    """RingCentral redirects here after the recruiter approves or denies
    consent. No @jwt_required - this request comes from RingCentral's
    server via the browser, not from our own frontend. Mirrors
    calendar_auth.py's microsoft_callback exactly, including landing back
    on the same Profile page (CALENDAR_FRONTEND_REDIRECT_URL is shared
    between both providers) with a query param it can read."""
    frontend_url = current_app.config['CALENDAR_FRONTEND_REDIRECT_URL']

    rc_error = request.args.get('error')
    if rc_error:
        return redirect(f'{frontend_url}?ringcentral_error={rc_error}')

    state = request.args.get('state')
    code = request.args.get('code')
    if not state or not code:
        return redirect(f'{frontend_url}?ringcentral_error=missing_code_or_state')

    try:
        payload = _state_serializer().loads(state, max_age=STATE_MAX_AGE_SECONDS)
    except SignatureExpired:
        return redirect(f'{frontend_url}?ringcentral_error=state_expired')
    except BadSignature:
        return redirect(f'{frontend_url}?ringcentral_error=invalid_state')

    user = User.query.get(payload['user_id'])
    if not user:
        return redirect(f'{frontend_url}?ringcentral_error=unknown_user')

    try:
        tokens = exchange_code_for_tokens(code)
        access_token = tokens['access_token']
        expires_in = tokens.get('expires_in', 3600)
        refresh_token = tokens.get('refresh_token')
    except Exception:
        current_app.logger.exception('RingCentral OAuth exchange failed')
        return redirect(f'{frontend_url}?ringcentral_error=token_exchange_failed')

    # Best-effort, separate from the exchange above: this app's "Video"
    # scope doesn't necessarily grant the Extension-info endpoint used here
    # (some accounts/plans 403 it) - that's fine, it's purely a display
    # label (RingCentralConnection.account_email), not something meeting
    # creation/recording retrieval depend on. A real, working connection
    # (the tokens above) shouldn't be thrown away over this.
    try:
        account_email = fetch_ringcentral_email(access_token)
    except Exception:
        current_app.logger.warning(
            'Could not fetch RingCentral account email for user %s - connecting anyway', user.id, exc_info=True,
        )
        account_email = None

    if not refresh_token:
        return redirect(f'{frontend_url}?ringcentral_error=no_refresh_token')

    connection = RingCentralConnection.query.filter_by(user_id=user.id).first()
    if not connection:
        connection = RingCentralConnection(user_id=user.id)
        db.session.add(connection)

    connection.encrypted_refresh_token = encrypt_token(refresh_token)
    connection.account_email = account_email or connection.account_email or ''
    connection.access_token = access_token
    connection.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
    db.session.commit()

    return redirect(f'{frontend_url}?ringcentral_connected=true')


@ringcentral_auth_bp.route('/api/auth/ringcentral/disconnect', methods=['DELETE'])
@jwt_required()
def ringcentral_disconnect():
    user_id = int(get_jwt_identity())
    connection = RingCentralConnection.query.filter_by(user_id=user_id).first()
    if not connection:
        return jsonify({"error": "no RingCentral connection to disconnect"}), 404

    db.session.delete(connection)
    db.session.commit()
    return '', 204


@ringcentral_auth_bp.route('/api/auth/ringcentral/status', methods=['GET'])
@jwt_required()
def ringcentral_status():
    """Same reasoning as calendar_auth.py's microsoft_status - connect/
    callback are full-page redirects with nothing the frontend can read
    directly, so it needs a way to ask "is my RingCentral connected?" on a
    normal page load.

    Unlike that first-pass version (and microsoft_status, which still has
    this same gap), `connected` alone isn't enough to answer that - a
    connection row existing only proves it worked *once*. RingCentral's
    refresh tokens are short-lived (~7 days) and rotate on every use, so a
    connection can go stale silently: booking still succeeds regardless
    (falls back to the interviewer's static link - see routes/apply.py's
    _create_ringcentral_meeting_or_fallback), but the Profile page would
    keep showing "Connected" forever with nothing to suggest otherwise.
    `healthy` actually attempts a token refresh here (a no-op if the
    cached access token is still good) and reports whether that succeeded
    - a real RingCentralTokenError (RingCentral explicitly rejected the
    refresh) means `healthy: False`; a transient network failure doesn't -
    that's not evidence the connection is actually broken, just that
    RingCentral (or this network) had a bad moment right now."""
    user_id = int(get_jwt_identity())
    connection = RingCentralConnection.query.filter_by(user_id=user_id).first()
    if not connection:
        return jsonify({"connected": False}), 200

    healthy = True
    try:
        get_valid_access_token(User.query.get(user_id))
    except RingCentralTokenError:
        healthy = False
    except requests.RequestException:
        current_app.logger.warning(
            "Could not verify RingCentral connection health for user %s (network error) - "
            "assuming still healthy", user_id, exc_info=True,
        )

    return jsonify({"connected": True, "account_email": connection.account_email, "healthy": healthy}), 200

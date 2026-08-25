import logging

import click
from flask import Flask, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate, upgrade
from config import Config
from extensions import limiter
from models import db, User
from routes.candidates import candidates_bp
from routes.jobs import jobs_bp
from routes.auth import auth_bp
from routes.calendar_auth import calendar_auth_bp
from routes.candidate_auth import candidate_auth_bp
from routes.interviews import interviews_bp
from routes.meeting_stages import meeting_stages_bp
from routes.screening_questions import screening_questions_bp
from routes.onboarding_items import onboarding_items_bp
from routes.organization import organization_bp
from routes.apply import apply_bp
from routes.status import status_bp

migrate = Migrate()


def create_app(config_overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    # Flask's app.logger comes with a stderr handler already attached, but
    # its effective level falls back to the interpreter's default (WARNING)
    # unless something sets it explicitly - which would silently swallow
    # every .info() call app-wide, including the one thing
    # email_sender.ConsoleEmailProvider exists to make visible (grabbing an
    # apply/confirmation link straight from the console in dev).
    app.logger.setLevel(logging.INFO)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    jwt = JWTManager(app)
    CORS(app)
    limiter.init_app(app)

    # Recruiter (User) and candidate (CandidateAccount) accounts are separate
    # identities issued from separate login flows — a token's `account_type`
    # claim says which (named that, not `type`, because flask-jwt-extended
    # already reserves a built-in `type` claim for "access" vs "refresh" —
    # reusing that name silently collides with it). Without this check, a
    # candidate token would pass @jwt_required() on recruiter routes just
    # fine (those don't check role at all yet — see README's "Known gaps"),
    # which is a real privilege-escalation path, not just a cosmetic
    # mismatch. Candidate routes live under /api/candidate/; everything else
    # is recruiter-only. Tokens issued before this claim existed have no
    # `account_type` and are treated as recruiter tokens, so existing
    # sessions aren't force-logged-out.
    @jwt.token_verification_loader
    def verify_token_type(_jwt_header, jwt_payload):
        account_type = jwt_payload.get('account_type', 'user')
        if request.path.startswith('/api/candidate/'):
            return account_type == 'candidate'
        return account_type == 'user'

    app.register_blueprint(candidates_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(calendar_auth_bp)
    app.register_blueprint(candidate_auth_bp)
    app.register_blueprint(interviews_bp)
    app.register_blueprint(meeting_stages_bp)
    app.register_blueprint(screening_questions_bp)
    app.register_blueprint(onboarding_items_bp)
    app.register_blueprint(organization_bp)
    app.register_blueprint(apply_bp)
    app.register_blueprint(status_bp)

    @app.route('/api/health', methods=['GET'])
    def health_check():
        return {"status": "ok"}, 200

    # Werkzeug enforces MAX_CONTENT_LENGTH (config.py, 15MB - applies to
    # every upload app-wide: resumes, onboarding documents, org logo/banner)
    # before any view function runs, raising RequestEntityTooLarge - which
    # Flask's default handling renders as a bare HTML error page. Every
    # other error response in this app is JSON with an "error" key (see
    # ApiError on the frontend), so without this override a too-large
    # upload would be the one response shape the frontend's error handling
    # can't parse a message out of.
    @app.errorhandler(413)
    def handle_file_too_large(_e):
        max_mb = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        return {"error": f"That file is too large - please upload something under {max_mb}MB."}, 413

    @app.cli.command('create-user')
    @click.option('--first-name', prompt=True)
    @click.option('--last-name', prompt=True)
    @click.option('--email', prompt=True)
    @click.option('--phone', default=None, help='Optional')
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option('--role', default='recruiter', help='admin, recruiter, or interviewer')
    def create_user(first_name, last_name, email, phone, password, role):
        """Create a user who can log in to the API. Run with: flask create-user"""
        if User.query.filter_by(email=email).first():
            click.echo(f'A user with email {email} already exists.')
            return

        user = User(first_name=first_name, last_name=last_name, email=email, phone=phone, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f'Created user {email} ({role}).')

    @app.cli.command('deactivate-user')
    @click.option('--email', prompt=True)
    def deactivate_user(email):
        """Deactivate a user so they can no longer log in. Run with: flask deactivate-user"""
        user = User.query.filter_by(email=email).first()
        if not user:
            click.echo(f'No user found with email {email}.')
            return
        if not user.is_active:
            click.echo(f'{email} is already deactivated.')
            return

        user.is_active = False
        db.session.commit()
        click.echo(f'Deactivated {email}. Note: any access token they already hold stays valid until it expires (default 15 min).')

    @app.cli.command('reset-password')
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    def reset_password(email, password):
        """Reset a user's password. Run with: flask reset-password"""
        user = User.query.filter_by(email=email).first()
        if not user:
            click.echo(f'No user found with email {email}.')
            return

        user.set_password(password)
        db.session.commit()
        click.echo(f'Password reset for {email}.')

    return app


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        # Applies any migrations under migrations/versions/ that haven't run
        # yet against this DB — the dev-convenience equivalent of `flask db
        # upgrade`, so `python3 app.py` alone is still enough to get running.
        upgrade()
    # Port 5000 is claimed by macOS's AirPlay Receiver (AirTunes) on most Macs,
    # which silently swallows requests before Flask ever sees them. 5050 avoids it.
    app.run(debug=True, port=5050)

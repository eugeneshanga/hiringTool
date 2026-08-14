import click
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db, User
from routes.candidates import candidates_bp
from routes.jobs import jobs_bp
from routes.auth import auth_bp
from routes.interviews import interviews_bp
from routes.meeting_stages import meeting_stages_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    JWTManager(app)
    CORS(app)

    app.register_blueprint(candidates_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(interviews_bp)
    app.register_blueprint(meeting_stages_bp)

    @app.route('/api/health', methods=['GET'])
    def health_check():
        return {"status": "ok"}, 200

    @app.cli.command('create-user')
    @click.option('--name', prompt=True)
    @click.option('--email', prompt=True)
    @click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option('--role', default='recruiter', help='admin, recruiter, or interviewer')
    def create_user(name, email, password, role):
        """Create a user who can log in to the API. Run with: flask create-user"""
        if User.query.filter_by(email=email).first():
            click.echo(f'A user with email {email} already exists.')
            return

        user = User(name=name, email=email, role=role)
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
        db.create_all()
    # Port 5000 is claimed by macOS's AirPlay Receiver (AirTunes) on most Macs,
    # which silently swallows requests before Flask ever sees them. 5050 avoids it.
    app.run(debug=True, port=5050)

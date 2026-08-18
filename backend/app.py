import click
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from sqlalchemy import inspect, text
from config import Config
from models import db, User, MeetingStageTemplate
from routes.candidates import candidates_bp
from routes.jobs import jobs_bp
from routes.auth import auth_bp
from routes.interviews import interviews_bp
from routes.meeting_stages import meeting_stages_bp
from routes.screening_questions import screening_questions_bp


def _add_missing_columns(inspector, table, columns):
    """columns: {name: SQL type}. Adds any that aren't in the table yet."""
    if table not in inspector.get_table_names():
        return
    existing_cols = {c['name'] for c in inspector.get_columns(table)}
    with db.engine.begin() as conn:
        for name, sql_type in columns.items():
            if name not in existing_cols:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}'))


def _migrate_users_split_name(inspector):
    """The `users` table used to have one `name` column; it's now first_name +
    last_name + phone. Add the new columns, backfill from the old one, then
    drop it (SQLite/Postgres both support DROP COLUMN)."""
    if 'users' not in inspector.get_table_names():
        return
    existing_cols = {c['name'] for c in inspector.get_columns('users')}
    if 'name' not in existing_cols:
        return

    _add_missing_columns(
        inspector, 'users',
        {'first_name': 'VARCHAR(120)', 'last_name': 'VARCHAR(120)', 'phone': 'VARCHAR(20)'},
    )
    with db.engine.begin() as conn:
        rows = conn.execute(text('SELECT id, name FROM users WHERE first_name IS NULL')).fetchall()
        for row in rows:
            first, _, last = (row.name or '').partition(' ')
            conn.execute(
                text('UPDATE users SET first_name = :first, last_name = :last WHERE id = :id'),
                {'first': first, 'last': last, 'id': row.id},
            )
        conn.execute(text('ALTER TABLE users DROP COLUMN name'))


def _run_light_migrations():
    """Add columns introduced after the table already existed. db.create_all()
    only creates missing tables, so a dev DB from before these columns were
    added needs them patched in by hand (no Flask-Migrate in this project)."""
    inspector = inspect(db.engine)

    _add_missing_columns(
        inspector, 'meeting_stage_templates',
        {'duration_minutes': 'INTEGER', 'sort_order': 'INTEGER'},
    )
    _add_missing_columns(
        inspector, 'candidates',
        {
            'city': 'VARCHAR(120)',
            'state': 'VARCHAR(60)',
            'source': 'VARCHAR(120)',
            'resume_original_filename': 'VARCHAR(255)',
            'resume_stored_filename': 'VARCHAR(255)',
            'updated_at': 'DATETIME',
        },
    )
    _migrate_users_split_name(inspector)

    if 'meeting_stage_templates' not in inspector.get_table_names():
        return

    # Backfill sort_order for any rows that don't have one yet, ordered per job
    # by id (their prior implicit order) so existing stage lists don't reshuffle.
    templates = MeetingStageTemplate.query.order_by(
        MeetingStageTemplate.job_id.asc(), MeetingStageTemplate.id.asc()
    ).all()
    counters = {}
    changed = False
    for t in templates:
        if t.sort_order is None:
            t.sort_order = counters.get(t.job_id, 0)
            counters[t.job_id] = t.sort_order + 1
            changed = True
        else:
            counters[t.job_id] = max(counters.get(t.job_id, 0), t.sort_order + 1)
    if changed:
        db.session.commit()


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
    app.register_blueprint(screening_questions_bp)

    @app.route('/api/health', methods=['GET'])
    def health_check():
        return {"status": "ok"}, 200

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
        db.create_all()
        _run_light_migrations()
    # Port 5000 is claimed by macOS's AirPlay Receiver (AirTunes) on most Macs,
    # which silently swallows requests before Flask ever sees them. 5050 avoids it.
    app.run(debug=True, port=5050)

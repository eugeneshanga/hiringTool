"""One-off script for DirectAdmin's Python App "Execute python script" tool -
creates a single admin User, since `flask create-user` normally prompts
interactively (via click.prompt), which doesn't work through this panel's
non-interactive script runner.

Reads credentials from environment variables rather than hardcoding them in
this file - set these under the Python App's "Environment variables"
section before running this script, then remove ADMIN_PASSWORD afterward
(the panel keeps env vars around; no reason to leave a plaintext password
sitting there once the user exists):
    ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_FIRST_NAME, ADMIN_LAST_NAME

Usage in the panel: path to this file, e.g.
    /home/theforev/domains/careers.fprecioushomecare.com/public_python/deploy_create_admin.py
No arguments needed. Safe to re-run - no-ops (with a message) if a user
with that email already exists, same as the `flask create-user` CLI command.
"""
import os

from app import create_app
from models import User, db

app = create_app()

email = os.environ.get('ADMIN_EMAIL')
password = os.environ.get('ADMIN_PASSWORD')
first_name = os.environ.get('ADMIN_FIRST_NAME')
last_name = os.environ.get('ADMIN_LAST_NAME')

missing = [name for name, value in [
    ('ADMIN_EMAIL', email), ('ADMIN_PASSWORD', password),
    ('ADMIN_FIRST_NAME', first_name), ('ADMIN_LAST_NAME', last_name),
] if not value]
if missing:
    raise SystemExit(f"Missing required environment variable(s): {', '.join(missing)}")

with app.app_context():
    if User.query.filter_by(email=email).first():
        print(f'A user with email {email} already exists - nothing to do.')
    else:
        user = User(first_name=first_name, last_name=last_name, email=email, role='admin')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f'Created admin user {email}.')

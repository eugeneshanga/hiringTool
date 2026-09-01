"""One-off script for DirectAdmin's Python App "Execute python script" tool -
runs the same migration upgrade flow as `flask db upgrade`, without needing
a real shell. Safe to re-run: Alembic no-ops if already at head.

Usage in the panel: path to this file, e.g.
    /home/theforev/domains/careers.fprecioushomecare.com/public_python/deploy_run_migrations.py
No arguments needed.
"""
from app import create_app
from flask_migrate import upgrade

app = create_app()
with app.app_context():
    upgrade()

print("Migrations complete.")

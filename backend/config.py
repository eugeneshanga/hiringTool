import os
from dotenv import load_dotenv

# load_dotenv() with no args only looks for a file named exactly ".env" - our
# env file is named database.env, so point at it explicitly.
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database.env')
load_dotenv(_ENV_PATH)


class Config:
    # Falls back to a local SQLite file when DATABASE_URL isn't set (e.g. local
    # dev without Postgres running). Set DATABASE_URL to point at real Postgres.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', 'sqlite:///' + os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hiringtool_dev.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Used to sign JWTs. Overridden via env var in any non-local environment.
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-secret-change-me')

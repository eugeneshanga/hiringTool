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

    # Resumes and onboarding documents get written here (dev only — a real
    # deployment should point this at object storage instead).
    UPLOAD_FOLDER = os.environ.get(
        'UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    )
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15MB per upload

    # Google Calendar OAuth (see database.env). Left unset in Config's fallback
    # rather than raising here so the app still boots (and the rest of the
    # test suite still runs) in environments that don't have calendar
    # integration configured yet — routes/calendar_auth.py is what actually
    # needs these to be present, and fails loudly there if they're missing.
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
    GOOGLE_REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI')
    CALENDAR_FRONTEND_REDIRECT_URL = os.environ.get('CALENDAR_FRONTEND_REDIRECT_URL', 'http://localhost:5173/')

    # Fernet key encrypting CalendarConnection.refresh_token at rest.
    CALENDAR_ENCRYPTION_KEY = os.environ.get('CALENDAR_ENCRYPTION_KEY')

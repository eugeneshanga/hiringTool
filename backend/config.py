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
    CALENDAR_FRONTEND_REDIRECT_URL = os.environ.get('CALENDAR_FRONTEND_REDIRECT_URL', 'http://localhost:5173/profile')

    # Fernet key encrypting CalendarConnection.refresh_token at rest.
    CALENDAR_ENCRYPTION_KEY = os.environ.get('CALENDAR_ENCRYPTION_KEY')

    # Candidate-visible scheduling availability (working hours/timezone/
    # allowed days) used to live here as env-var-only settings. It's now
    # editable from the Organization Settings page instead - see
    # Organization.scheduling_timezone etc. in models.py and
    # google_calendar.get_free_slots, which reads from there.

    # Where the frontend lives, for building links this backend emails out
    # (e.g. the public apply/schedule link - see routes/apply.py and
    # email_sender.py). Distinct from CALENDAR_FRONTEND_REDIRECT_URL above,
    # which is a specific full redirect target rather than a base to build
    # paths onto.
    FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:5173')

    # Which EmailProvider (see email_sender.py) sends application-related
    # email - 'console' (default, logs instead of sending) or 'postmark'.
    EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER', 'console')

    # Required when EMAIL_PROVIDER=postmark. Server token from the Postmark
    # dashboard (Servers -> your server -> API Tokens), and the From address
    # that server's Sender Signature (or a verified sending domain) was set
    # up for - Postmark rejects a send whose From isn't verified on that
    # server. Left unset in Config's fallback, same as the Google Calendar
    # vars above - PostmarkEmailProvider is what fails loudly if these are
    # missing while actually needed, not app startup.
    POSTMARK_SERVER_TOKEN = os.environ.get('POSTMARK_SERVER_TOKEN')
    EMAIL_FROM_ADDRESS = os.environ.get('EMAIL_FROM_ADDRESS')

    # Flask-Limiter's storage backend (see extensions.py). In-memory by
    # default - fine for one dev process or the test suite, but each worker
    # process would keep its own separate counts, so a real multi-worker
    # deployment should set this to a shared store, e.g.
    # RATELIMIT_STORAGE_URI=redis://localhost:6379.
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')

    # Runs the in-process APScheduler background job that sends delayed
    # rejection emails (see scheduled_jobs.py) - off in tests (conftest.py's
    # `app` fixture overrides this) so pytest never spins up a real
    # background thread. Same "single process only" caveat as
    # RATELIMIT_STORAGE_URI/email_sender's send cap above - a multi-worker
    # deployment would need a real task queue instead.
    SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'true').lower() == 'true'

    # How long after being auto-disqualified by screening answers (see
    # routes/apply.py) a candidate's rejection email actually goes out -
    # deliberately not instant, so it doesn't read as an obviously automated
    # reply. Minutes, not hours, so it's easy to turn down for testing/demo
    # without a code change.
    REJECTION_EMAIL_DELAY_MINUTES = int(os.environ.get('REJECTION_EMAIL_DELAY_MINUTES', '60'))

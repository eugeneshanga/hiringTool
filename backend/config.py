import os
from dotenv import load_dotenv

# load_dotenv() with no args only looks for a file named exactly ".env" - our
# env file is named database.env, so point at it explicitly.
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'database.env')
load_dotenv(_ENV_PATH)


class Config:
    # Falls back to a local SQLite file when DATABASE_URL isn't set (e.g. local
    # dev without MariaDB running). Set DATABASE_URL to point at the real
    # MariaDB instance in production, e.g.
    # mysql+pymysql://user:password@localhost/dbname - PyMySQL (see
    # requirements.txt) is the driver behind that mysql+pymysql:// scheme.
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
    # Bounds every upload in the app (resumes, onboarding documents, org
    # logo/banner, interview recordings). Sized for the largest of these -
    # interview recordings (see routes/candidates.py's MAX_RECORDING_SIZE_BYTES,
    # which should stay <= this) - everything else has its own, much smaller
    # cap enforced in its own route on top of this.
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB per upload

    # Microsoft/Outlook Calendar OAuth (see database.env), via an Entra ID
    # (Azure AD) app registration - Client ID/Secret from that app's
    # "Certificates & secrets" page, Redirect URI matching what's registered
    # there. Left unset in Config's fallback rather than raising here so the
    # app still boots (and the rest of the test suite still runs) in
    # environments that don't have calendar integration configured yet —
    # routes/calendar_auth.py is what actually needs these to be present,
    # and fails loudly there if they're missing.
    MICROSOFT_CLIENT_ID = os.environ.get('MICROSOFT_CLIENT_ID')
    MICROSOFT_CLIENT_SECRET = os.environ.get('MICROSOFT_CLIENT_SECRET')
    MICROSOFT_REDIRECT_URI = os.environ.get('MICROSOFT_REDIRECT_URI')
    # 'common' accepts both work/school and personal Microsoft accounts -
    # narrow this to 'organizations' (work/school only) or a specific
    # tenant ID if the company wants to lock out personal accounts.
    MICROSOFT_TENANT = os.environ.get('MICROSOFT_TENANT', 'common')
    CALENDAR_FRONTEND_REDIRECT_URL = os.environ.get('CALENDAR_FRONTEND_REDIRECT_URL', 'http://localhost:5173/profile')

    # RingCentral OAuth (see database.env), via a RingCentral Developer
    # Console app registration (private, 3-legged auth-code flow, "Video"
    # scope) - same "left unset, fails loudly in routes/ringcentral_auth.py
    # instead" reasoning as the Microsoft settings above. Reuses
    # CALENDAR_FRONTEND_REDIRECT_URL (same Profile page) and
    # CALENDAR_ENCRYPTION_KEY (same Fernet key encrypting refresh tokens at
    # rest, for both providers) rather than duplicating either.
    RINGCENTRAL_CLIENT_ID = os.environ.get('RINGCENTRAL_CLIENT_ID')
    RINGCENTRAL_CLIENT_SECRET = os.environ.get('RINGCENTRAL_CLIENT_SECRET')
    RINGCENTRAL_REDIRECT_URI = os.environ.get('RINGCENTRAL_REDIRECT_URI')

    # Google reCAPTCHA v2 ("I'm not a robot" checkbox) on the recruiter
    # login form (routes/auth.py, LoginPage.tsx) - from
    # google.com/recaptcha/admin. Only the secret is needed here: the site
    # key is public by design (embedded in the built frontend via Vite's
    # VITE_RECAPTCHA_SITE_KEY, not read from this backend config at all).
    # Left unset, login skips the check entirely (recaptcha.py's
    # verify_recaptcha is never called) - true in local dev/tests unless
    # this is explicitly set, same "unconfigured = feature no-ops" pattern
    # as the calendar integrations above.
    RECAPTCHA_SECRET_KEY = os.environ.get('RECAPTCHA_SECRET_KEY')

    # Fernet key encrypting CalendarConnection.refresh_token at rest.
    CALENDAR_ENCRYPTION_KEY = os.environ.get('CALENDAR_ENCRYPTION_KEY')

    # Candidate-visible scheduling availability (working hours/timezone/
    # allowed days) used to live here as env-var-only settings. It's now
    # editable from the Organization Settings page instead - see
    # Organization.scheduling_timezone etc. in models.py and
    # microsoft_calendar.get_free_slots, which reads from there.

    # Where the frontend lives, for building links this backend emails out
    # (e.g. the public apply/schedule link - see routes/apply.py and
    # email_sender.py). Distinct from CALENDAR_FRONTEND_REDIRECT_URL above,
    # which is a specific full redirect target rather than a base to build
    # paths onto.
    FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:5173')

    # Which EmailProvider (see email_sender.py) sends application-related
    # email - 'console' (default, logs instead of sending), 'postmark', or
    # 'resend'.
    EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER', 'console')

    # Required when EMAIL_PROVIDER=postmark. Server token from the Postmark
    # dashboard (Servers -> your server -> API Tokens), and the From address
    # that server's Sender Signature (or a verified sending domain) was set
    # up for - Postmark rejects a send whose From isn't verified on that
    # server. Left unset in Config's fallback, same as the Microsoft Calendar
    # vars above - PostmarkEmailProvider is what fails loudly if these are
    # missing while actually needed, not app startup.
    POSTMARK_SERVER_TOKEN = os.environ.get('POSTMARK_SERVER_TOKEN')
    # Required when EMAIL_PROVIDER=resend. API key from the Resend
    # dashboard - like POSTMARK_SERVER_TOKEN, left unset in Config's
    # fallback; ResendEmailProvider is what fails loudly if it's missing
    # while actually needed, not app startup.
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
    # From address for whichever of the two above is active - shared since
    # only one provider is ever selected at a time.
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

    # Forces a redirect to HTTPS for any request that arrives over plain
    # HTTP (see app.py's before_request hook) - off by default so local dev
    # (http://localhost:5050, no TLS at all) isn't affected. Set to 'true'
    # only in the production database.env, once HTTPS is confirmed actually
    # reachable there.
    FORCE_HTTPS = os.environ.get('FORCE_HTTPS', 'false').lower() == 'true'

    # Content-Security-Policy sent on every response (see app.py's
    # after_request hook). This is a single same-origin Flask process
    # serving both the API and the Vite-built SPA, with no CDN scripts and
    # no inline <script>/<style> in the built index.html, so a strict policy
    # needs no per-request nonces. Kept as one overridable string so a
    # single directive can be widened (e.g. an extra connect-src host)
    # without a code change. Set to '' to drop the header entirely.
    CONTENT_SECURITY_POLICY = os.environ.get(
        'CONTENT_SECURITY_POLICY',
        "default-src 'self'; "
        # www.google.com/www.gstatic.com - the reCAPTCHA widget on the login
        # page (LoginPage.tsx): api.js itself, and the challenge iframe it
        # renders (frame-src below). Only reachable at all once
        # VITE_RECAPTCHA_SITE_KEY is set at build time - otherwise the
        # widget never mounts and these hosts are simply never contacted.
        "script-src 'self' https://www.google.com https://www.gstatic.com; "
        "style-src 'self'; "
        # blob: - the org logo/banner is fetched via JS (it's behind auth)
        # and shown as <img src> from a blob: object URL (UserMenu.tsx,
        # OrganizationSettingsPage.tsx, useOrganizationBranding.ts) rather
        # than a plain <img src="/api/..."> - a blob: URL for an <img> can
        # only ever render as a bitmap, never execute, so this doesn't
        # reopen anything the upload hardening closed.
        "img-src 'self' data: blob:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-src https://www.google.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    # When true, the policy goes out as Content-Security-Policy-Report-Only:
    # browsers log violations to the console but don't block anything.
    # Defaults to true so a first deploy can't white-screen the app on an
    # unforeseen violation - set CSP_REPORT_ONLY=false in production once the
    # console is confirmed clean, to actually enforce it.
    CSP_REPORT_ONLY = os.environ.get('CSP_REPORT_ONLY', 'true').lower() == 'true'

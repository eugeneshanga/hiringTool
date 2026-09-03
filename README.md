# hiringTool

An in-house applicant tracking system: job postings, candidate pipelines, and
interview/orientation scheduling. Flask + SQLAlchemy API backend, React +
Vite + TypeScript frontend.

## Stack

- **Backend:** Flask, Flask-SQLAlchemy, Flask-Migrate (Alembic), Flask-JWT-Extended,
  Flask-Limiter. SQLite for local dev (falls back automatically); production
  points `DATABASE_URL` at a real MariaDB instance via PyMySQL
  (`mysql+pymysql://...`).
- **Frontend:** React 19, Vite, TypeScript, React Router

## Setup

### Backend

```bash
cd backend
python3 -m venv ../venv        # first time only
source ../venv/bin/activate
pip install -r requirements.txt
flask db upgrade                # applies migrations (creates the DB on first run)
```

Recruiter/admin accounts are provisioned directly — there's no self-service
registration (an admin creates every account):

```bash
flask create-user   # prompts for first/last name, email, password; --role for admin/interviewer
```

Run the API:

```bash
python3 app.py
```

Serves on **http://127.0.0.1:5050**. `python3 app.py` also runs any pending migrations on
startup, so a fresh clone just needs `pip install` + this to be up to date.

Other user-management commands:

```bash
flask deactivate-user --email someone@example.com   # blocks future logins
flask reset-password --email someone@example.com    # sets a new password
```

### Database migrations

Schema changes go through Flask-Migrate/Alembic — never hand-edit the dev DB.

```bash
# after changing a model in models.py:
flask db migrate -m "describe the change"   # autogenerates migrations/versions/<rev>_*.py
# review the generated file, then:
flask db upgrade                            # applies it
```

`migrations/env.py` is configured with `render_as_batch=True`, which SQLite
needs for anything beyond adding a column (dropping/altering columns,
constraints, etc.) — that's already handled, no extra flags needed.

### Tests

```bash
cd backend
source ../venv/bin/activate
pytest
```

Tests run against an in-memory SQLite DB (see `tests/conftest.py`) and never
touch `hiringtool_dev.db`. Coverage is deliberately concentrated on the
trickiest logic — enroll/unenroll capacity handling, the meeting-stage-rename
cascade, Microsoft Calendar OAuth/availability/booking (mocked at the
Graph API edge), and the onboarding-visibility/rejection-cascade rules
around candidate stage status — rather than every route.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Serves on **http://localhost:5173**. Reads the API URL from
`frontend/.env` (`VITE_API_URL`, defaults to `http://127.0.0.1:5050`) — copy
`.env.example` if you don't have one yet.

### Deploying

Production runs on HostPinnacle (DirectAdmin) — see
**[DEPLOYMENT.md](DEPLOYMENT.md)** for the full runbook.
`scripts/build_deploy_package.sh` builds the deploy zip; everything after
that is a manual File Manager upload (no SSH on this hosting plan, and
DirectAdmin's Git integration doesn't support this deployment's subdomain).

## Environment / config

- `database.env` (repo root) — set `DATABASE_URL` here to point at a real
  MariaDB instance (`mysql+pymysql://user:password@host/dbname` — PyMySQL is
  the driver behind that scheme). Left unset, `backend/config.py` falls back
  to a local SQLite file (`backend/hiringtool_dev.db`).
- `database.env` also holds Microsoft/Outlook Calendar OAuth config, from an
  Entra ID (Azure AD) app registration: `MICROSOFT_CLIENT_ID`,
  `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_REDIRECT_URI`, `MICROSOFT_TENANT`
  (`common` by default — accepts both work/school and personal Microsoft
  accounts), `CALENDAR_FRONTEND_REDIRECT_URL` (where the OAuth callback sends
  the browser back to), and `CALENDAR_ENCRYPTION_KEY` (a Fernet key
  encrypting stored refresh tokens at rest — generate one with
  `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`;
  rotating it invalidates every stored refresh token).
- `database.env` also controls outbound email (see `backend/email_sender.py`):
  `EMAIL_PROVIDER` — `console` (default; logs the email instead of sending,
  no external account needed), `postmark`, or `resend`. Both real providers
  share `EMAIL_FROM_ADDRESS` (must be a verified sender in that provider's
  account — unverified senders get rejected) plus their own API key:
  `POSTMARK_SERVER_TOKEN` (Postmark dashboard → your Server → API Tokens) or
  `RESEND_API_KEY` (Resend dashboard). A brand-new Postmark account starts in
  trial mode, which can only deliver to recipients on the same domain as
  `EMAIL_FROM_ADDRESS` until you request full sending approval from Postmark.
  Every `to_email` this module sends to — regardless of provider — is
  validated by `is_plausible_email()` first, closing off header injection
  via a crafted address like `victim@x.com\r\nBcc: attacker@evil.com`.
- `FORCE_HTTPS` — unset/`false` by default (local dev has no TLS to redirect
  to). Set to `true` only in production, once HTTPS is confirmed reachable
  there — see DEPLOYMENT.md.
- `frontend/.env` — `VITE_API_URL`, the backend's address.

Neither file is committed (see `.gitignore`); both have `.example`-style
defaults documented above.

## Features so far

- **Auth (recruiter side)** — JWT login only, no self-service registration;
  every account (`admin`/`recruiter`/`interviewer`) is provisioned by an
  admin via `flask create-user --role`. Org settings and user management are
  admin-only (`auth_helpers.admin_required`); jobs/candidates/interviews
  don't yet differentiate recruiter vs. interviewer — see Known gaps.
- **Public careers site** (`/`, `routes/public.py`) — an unauthenticated
  landing page listing every Published job (org name/logo, title, pipe-
  separated type/location/salary, an in-place "Show Details" accordion, and
  a "Direct Link" for pointing a job board post like Indeed straight at that
  job's apply page), plus a persistent header carrying the org's branding
  across every public page (`/`, `/apply/job/:id`, `/apply/schedule/:token`,
  `/status`).
- **Candidates never get their own login** — there's no candidate-side
  account system at all. After applying, a candidate's only touchpoint is
  the public status page (`/status`, `routes/status.py`): look up by
  confirmation code (from the booking email), recover a lost code by email
  (`POST /api/status/resend-code` — never reveals whether a match was
  found, only ever triggers an email), and upload onboarding documents
  against their application (`POST /api/status/documents`) — all
  unauthenticated by design, gated only by the confirmation code. The
  onboarding checklist itself only appears once a decision's been made (see
  the status vocabulary below) — a candidate never sees "please upload your
  license" before anyone's decided their interview went well.
- **Jobs** — postings with type/location/salary/highlights/description,
  status (Published/Draft/Closed), and a numbered/reorderable **meeting
  stage** list per job (e.g. a "Virtual interview" stage named "CHHA"
  followed by an "In-person orientation" stage).
- **Meeting stage editor** — clicking a stage (from the job's stage list or
  from an upcoming session on the Home page) opens a dedicated editor with
  its own sidebar: rename/retype the stage, a **Pre-screen** tab (that
  stage's own qualifying questions — plain or multiple-choice with which
  answers qualify/disqualify a candidate), and a **Schedule** tab for
  interview-length/scheduling-window settings plus managing its scheduled
  **sessions** (add, delete, enroll/unenroll candidates, capacity limits). A
  header "Schedule interview" button covers the common case in one modal:
  search or add a candidate, then pick an open slot off a small calendar or
  spin up a custom one-off time. A stage — interview stages always, an
  orientation stage optionally — can also be assigned an interviewer +
  duration to get real Microsoft Calendar availability wired into its
  scheduling instead of (or alongside) the plain session/capacity system.
- **Candidates** — pipeline stage (Applied → Interview → Offer → Hired /
  Rejected), search/filtering/CSV export, and a full candidate detail page:
  contact info, resume upload, per-stage scheduling + a status dropdown
  (`Upcoming`, `Yes`, `Yes - Awaiting information`, `Yes - Information
  received`, `No`, `Maybe`, `Hired`, `No show`, `No response`, `Needs
  review`) + notes + 1–5 scorecard + an uploaded interview recording
  (video, played back in place once uploaded), the onboarding document
  checklist (upload/download, incl. a zip of everything — gated on the
  candidate's own side per the status above), and answers to the job's
  pre-screening questions. Setting a stage's status to `No` (or using the
  "Cancel interview" action, which sets the same status) cascades: the
  candidate's overall pipeline stage flips to `Rejected`, and the same
  delayed rejection email fires as the automatic screening-based path
  (`scheduled_jobs.send_due_rejection_emails`). Once every required
  onboarding item for a stage has a submission, `Yes - Awaiting information`
  advances itself to `Yes - Information received` automatically.
- **Home / Upcoming** — scheduled interview sessions (1:1 or capacity-limited
  group sessions like an orientation), with enroll/unenroll per candidate.
  Enrolling a candidate automatically advances their stage to "Interview"
  (manual overrides on the Candidates page still work). Clicking a session
  opens its meeting stage editor.
- **Microsoft/Outlook Calendar connection** — a `User` can connect their own
  Microsoft Calendar from their Profile page (`GET /api/auth/microsoft/connect`
  → Microsoft consent → `GET /api/auth/microsoft/callback`, `DELETE
  /api/auth/microsoft/disconnect`, `GET /api/auth/microsoft/status`). One
  connection per `User`, reusable across every stage they interview for —
  not tied to a job or stage. Refresh tokens are encrypted at rest
  (`CalendarConnection.encrypted_refresh_token`, Fernet) and rotated on use
  where Microsoft issues a new one; `microsoft_calendar.get_valid_access_token(user)`
  is what every later step calls for a live access token, refreshing
  automatically. `microsoft_calendar.get_free_slots` reads real availability
  (Graph's `calendar/getSchedule`) bounded to the org's configured working
  hours/timezone/days (Organization Settings), and booking (public apply
  flow or a recruiter booking a stage directly from a candidate's page)
  creates a real calendar event via Graph. The actual meeting link
  candidates and interviewers see isn't calendar-generated, though — each
  `User` sets their own static video-meeting link (RingCentral in practice)
  on their Profile page, and that's what goes out in confirmation
  emails/status pages/the calendar event's location.

## Known gaps

- No role-based permission checks on jobs/candidates/interviews — any
  logged-in `User` (admin/recruiter/interviewer alike) can do anything on
  those routes. (Org settings/user management are admin-only, and
  candidate-vs-recruiter is enforced everywhere — this gap is specifically
  about the three recruiter roles not being differentiated from each other
  elsewhere.)
- No frontend test coverage (backend has pytest; nothing exercises the React
  side yet).
- `CORS(app)` (app.py) has no restricted origin list — flagged, not acted
  on yet.
- ~~Login has no rate limiting~~ — fixed: `POST /api/auth/login` is now
  rate-limited both per-IP (20/hour) and per-email attempted (10/hour,
  `routes/auth.py`'s `_login_email_rate_limit_key`), so neither rotating
  IPs against one account nor spraying guesses across many accounts from
  one IP gets far.
- ~~No enforced HTTP→HTTPS redirect~~ — fixed at the app level
  (`app.py`'s `before_request` hook, gated by `FORCE_HTTPS` -
  see DEPLOYMENT.md for the production setup/verification step). Only
  active when explicitly turned on in production; deliberately a no-op
  whenever it can't be sure the original request was actually plain HTTP,
  rather than risk a redirect loop.
- Resume/onboarding-document/interview-recording storage is local disk under
  `backend/uploads/` — fine for one dev machine or single-worker deployment,
  not for a real multi-instance one.
- Jobs list has no kebab/bulk actions.
- `Interview.meeting_type` and `MeetingStageTemplate.meeting_type` use two
  different, overlapping vocabularies (a mapping function bridges them when
  scheduling a session from the stage editor) — worth unifying if either one
  grows further.

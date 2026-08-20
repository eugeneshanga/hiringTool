# hiringTool

An in-house applicant tracking system: job postings, candidate pipelines, and
interview/orientation scheduling. Flask + SQLAlchemy API backend, React +
Vite + TypeScript frontend.

## Stack

- **Backend:** Flask, Flask-SQLAlchemy, Flask-Migrate (Alembic), Flask-JWT-Extended,
  SQLite for local dev (falls back automatically; point `DATABASE_URL` at
  Postgres for anything beyond that)
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

Accounts can either self-register (see Auth below, `POST /api/auth/register`
via the frontend's `/register` page — always created as `recruiter`) or be
provisioned directly:

```bash
flask create-user   # prompts for first/last name, email, password; --role for admin/interviewer
```

Run the API:

```bash
python3 app.py
```

Serves on **http://127.0.0.1:5050**. (Not 5000 — macOS's AirPlay Receiver
squats on that port by default and will silently swallow requests before
Flask ever sees them.) `python3 app.py` also runs any pending migrations on
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
trickiest logic — enroll/unenroll capacity handling, the register flow, and
the meeting-stage-rename cascade — rather than every route.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Serves on **http://localhost:5173**. Reads the API URL from
`frontend/.env` (`VITE_API_URL`, defaults to `http://127.0.0.1:5050`) — copy
`.env.example` if you don't have one yet.

## Environment / config

- `database.env` (repo root) — set `DATABASE_URL` here to point at Postgres.
  Left unset, `backend/config.py` falls back to a local SQLite file
  (`backend/hiringtool_dev.db`).
- `database.env` also holds Google Calendar OAuth config: `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `CALENDAR_FRONTEND_REDIRECT_URL`
  (where the OAuth callback sends the browser back to), and
  `CALENDAR_ENCRYPTION_KEY` (a Fernet key encrypting stored refresh tokens at
  rest — generate one with
  `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`;
  rotating it invalidates every stored refresh token).
- `frontend/.env` — `VITE_API_URL`, the backend's address.

Neither file is committed (see `.gitignore`); both have `.example`-style
defaults documented above.

## Features so far

- **Auth (recruiter side)** — JWT login, plus self-service registration
  (`/register` on the frontend) for `recruiter` accounts. `admin`/
  `interviewer` roles are only granted via `flask create-user --role`.
- **Auth (candidate side)** — a separate login identity (`CandidateAccount`,
  distinct from the recruiter `User` model) at `/apply/register` and
  `/apply/login`, landing on a bare `/apply` home page once signed in. This
  is the first slice of flipping the app to also work from a prospective
  candidate's point of view — browsing/applying to jobs isn't built yet.
  Candidate and recruiter tokens are both JWTs but carry an `account_type`
  claim (`user` vs `candidate`) that `app.py`'s `token_verification_loader`
  enforces, so one can never be used as the other — see the comment there,
  since recruiter routes don't do their own role checks yet (next bullet).
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
  spin up a custom one-off time.
- **Candidates** — pipeline stage (Applied → Interview → Offer → Hired /
  Rejected), search/filtering/CSV export, and a full candidate detail page:
  contact info, resume upload, per-stage scheduling + status + notes +
  1–5 scorecard, the fixed onboarding document checklist (upload/download,
  incl. a zip of everything), and answers to the job's pre-screening
  questions.
- **Home / Upcoming** — scheduled interview sessions (1:1 or capacity-limited
  group sessions like an orientation), with enroll/unenroll per candidate.
  Enrolling a candidate automatically advances their stage to "Interview"
  (manual overrides on the Candidates page still work). Clicking a session
  opens its meeting stage editor.
- **Google Calendar connection (Phase 1)** — a `User` can connect their own
  Google Calendar (`GET /api/auth/google/connect` → Google consent → `GET
  /api/auth/google/callback`, `DELETE /api/auth/google/disconnect`, `GET
  /api/auth/google/status`). One connection per `User`, reusable across every
  stage they interview for — not tied to a job or stage. Refresh tokens are
  encrypted at rest (`CalendarConnection.encrypted_refresh_token`, Fernet);
  `google_calendar.get_valid_access_token(user)` is the helper later phases
  should call to get a live access token, refreshing automatically. Nothing
  reads or writes actual calendar events yet — see Known gaps.

## Known gaps

- No role-based permission checks *within* the recruiter side yet — any
  logged-in `User` (admin/recruiter/interviewer alike) can do anything on
  recruiter routes. (Candidate vs. recruiter is enforced, per the Auth
  bullet above — this gap is about the three recruiter roles not being
  differentiated from each other.)
- Registering a `CandidateAccount` creates a matching, unassigned (`job_id`
  null) `Candidate` row so recruiters see them on the Candidates list right
  away (linked via `Candidate.candidate_account_id`) — but that's as far as
  the linkage goes today. There's no "apply to a job" flow yet to attach a
  candidate to a specific posting, so every self-registered candidate stays
  unassigned until a recruiter manually assigns them a job.
- No frontend test coverage (backend has pytest; nothing exercises the React
  side yet).
- Google Calendar integration only has the connect/disconnect plumbing so
  far (see Features above) — no UI to connect from yet, no availability
  windows, and nothing actually reads/writes Google Calendar events for
  scheduling. Also undecided: whether an already-booked `Interview` should
  be affected if the interviewer later disconnects their calendar or changes
  their availability.
- Resume/onboarding-document storage is local disk under `backend/uploads/`
  — fine for one dev machine, not for a real multi-instance deployment.
- Jobs list has no kebab/bulk actions, and there's no public job-board/embed
  flow.
- `Interview.meeting_type` and `MeetingStageTemplate.meeting_type` use two
  different, overlapping vocabularies (a mapping function bridges them when
  scheduling a session from the stage editor) — worth unifying if either one
  grows further.

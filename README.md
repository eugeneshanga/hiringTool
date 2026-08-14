# hiringTool

An in-house applicant tracking system: job postings, candidate pipelines, and
interview/orientation scheduling. Flask + SQLAlchemy API backend, React +
Vite + TypeScript frontend.

## Stack

- **Backend:** Flask, Flask-SQLAlchemy, Flask-JWT-Extended, SQLite for local
  dev (falls back automatically; point `DATABASE_URL` at Postgres for
  anything beyond that)
- **Frontend:** React 19, Vite, TypeScript, React Router

## Setup

### Backend

```bash
cd backend
python3 -m venv ../venv        # first time only
source ../venv/bin/activate
pip install -r requirements.txt
```

Create a user (there's no public sign-up screen — this is an internal tool):

```bash
flask create-user
```

Run the API:

```bash
python3 app.py
```

Serves on **http://127.0.0.1:5050**. (Not 5000 — macOS's AirPlay Receiver
squats on that port by default and will silently swallow requests before
Flask ever sees them.)

Other user-management commands:

```bash
flask deactivate-user --email someone@example.com   # blocks future logins
flask reset-password --email someone@example.com    # sets a new password
```

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
- `frontend/.env` — `VITE_API_URL`, the backend's address.

Neither file is committed (see `.gitignore`); both have `.example`-style
defaults documented above.

## Features so far

- **Auth** — JWT login, no self-registration; accounts are provisioned via
  the `flask create-user` CLI.
- **Jobs** — postings with type/location/salary/highlights/description,
  status (Published/Draft/Closed), and a **meeting stage template** per job
  (e.g. an "Interview" stage named "CHHA" followed by an "Orientation"
  stage) shown as chips on the jobs list.
- **Candidates** — pipeline stage (Applied → Interview → Offer → Hired /
  Rejected), search and filtering.
- **Home / Upcoming** — scheduled interview sessions (1:1 or capacity-limited
  group sessions like an orientation), with enroll/unenroll per candidate.
  Enrolling a candidate automatically advances their stage to "Interview"
  (manual overrides on the Candidates page still work).

## Known gaps

- No database migration tool (Flask-Migrate/Alembic) — schema changes so far
  have been applied by hand against the dev db. Worth setting up before the
  schema moves much more.
- No role-based permission checks yet — any logged-in user can do anything.
- No resume upload or candidate detail page.
- Jobs list has no kebab/bulk actions, and there's no "Invite candidates" or
  public job-board/embed flow.

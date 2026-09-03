# Deploying to HostPinnacle (DirectAdmin)

Production runs as a DirectAdmin "Python App" (Phusion Passenger) at
`careers.fprecioushomecare.com`, backed by a MariaDB database. This
document is the actual runbook - follow it in order for every deploy.
`scripts/build_deploy_package.sh` automates the packaging step; everything
after that is manual through DirectAdmin's panel, for reasons explained
below.

## Why this is manual (no SSH, no working Git integration)

- **No shell access.** This hosting plan doesn't include SSH (`Shell
  Access` is disabled in Account Info) - ask HostPinnacle support if that
  ever changes; it would make this whole process much simpler (`git pull`
  + a couple commands instead of the below).
- **DirectAdmin's Git tool won't target this subdomain.** Its "Initialize
  Repository" form only lists top-level/additional domains in its Domain
  field (a fixed dropdown, not free text), not `careers.fprecioushomecare.com`
  as a subdomain of `fprecioushomecare.com` - and there's no Path override
  field to work around it. If `careers.` is ever recreated as a full
  Additional Domain instead of a Subdomain, this might start working; until
  then, deployment is: build a zip locally, upload + extract it through
  File Manager.

## One-time setup (already done - reference only)

The DirectAdmin **Python App** at `careers.fprecioushomecare.com` is
configured as:
- Python version: 3.11.15
- Application root: `domains/careers.fprecioushomecare.com/public_python`
- Application startup file: `wsgi_entry.py` **(not `passenger_wsgi.py`)**
- Application Entry point: `application`

**Why not `passenger_wsgi.py`:** DirectAdmin auto-generates its own
top-level `passenger_wsgi.py` in the app root (Phusion Passenger always
looks for that exact filename), templated as:
```python
wsgi = imp.load_source('wsgi', '<your Application startup file>')
application = wsgi.application
```
If our own entry script is also named `passenger_wsgi.py`, it collides
with DirectAdmin's own wrapper of the same name (the wrapper tries to load
itself). Our real entry point is `backend/wsgi_entry.py` - never rename it
back to `passenger_wsgi.py`, and never touch DirectAdmin's own
`passenger_wsgi.py` file directly; leave it as the panel manages it.

## Every deploy

1. **Build the package:**
   ```bash
   ./scripts/build_deploy_package.sh
   ```
   Produces `~/Desktop/hiringTool-deploy.zip`. It rebuilds the frontend
   with a production-safe (relative) API URL, stages `backend/`'s contents
   under `public_python/` and `frontend/`'s under `frontend/`, and refuses
   to produce a zip that's missing `wsgi_entry.py`, contains a colliding
   `passenger_wsgi.py`, or still has a localhost API URL baked into the
   built JS.

2. **Upload it** via DirectAdmin's File Manager into
   `domains/careers.fprecioushomecare.com/` - the folder that's a sibling
   of `public_html` and `public_python`, **not** inside `public_python/`
   itself.

3. **Extract it there, with "Merge and overwrite" checked.** File
   Manager's extractor does *not* merge by default - unchecked, it silently
   skips any top-level folder that already exists (which `public_python/`
   always will, after the first deploy), meaning none of your new code
   actually lands. This is the single easiest step to get wrong.

4. **If `requirements.txt` changed:** in the Python App page, under
   Configuration files, make sure `requirements.txt` is listed (add it via
   "Add another file and press enter" if the list is empty), then click
   **Run Pip Install**. Ignore a scary-looking "content type before/after
   doesn't match" error here if the install genuinely ran (it usually has
   — see step 6) - that's DirectAdmin's own post-install health check
   comparing `Content-Type` headers too literally (`text/html` vs
   `text/html; charset=utf-8`), not a real pip failure.

5. **If there are new migrations:** in "Execute python script", run:
   ```
   /home/theforev/domains/careers.fprecioushomecare.com/public_python/deploy_run_migrations.py
   ```
   Check the output starts with `Context impl MySQLImpl.` - if it says
   `Context impl SQLiteImpl.` instead, `database.env` isn't being found
   (see below) and this just migrated a throwaway local SQLite file, not
   the real database.

6. **Restart the app** so Passenger actually picks up the new code -
   on the **Web Applications** list page (not the edit page), the row for
   `careers.fprecioushomecare.com/` has an Actions column with four icons:
   a black square (**Stop**), a circular arrow (**Restart** - use this
   one), a pencil (edit settings), and a trash can (**destroy** - deletes
   the whole app config, not a takedown tool, see below). Installing
   dependencies or running a script does **not** by itself guarantee
   already-running application code gets reloaded - always restart after
   a deploy.

## Taking the site down temporarily

Same Actions column, the black square icon - its tooltip is "Stop the
application". The circular arrow next to it restarts (starts it back up).
**Don't use the trash-can icon for this** - that's destroy/delete, not
stop, and removes the app's configuration entirely.

Stop likely shows Passenger's own generic error page to visitors rather
than a branded "back soon" message - fine for a quick admin-side takedown,
but if a nicer visitor-facing maintenance page ever matters, that's worth
building as a `MAINTENANCE_MODE` check in `app.py` instead.

7. **Verify**: load `https://careers.fprecioushomecare.com` and click
   through anything the change actually touches.

## `database.env` location - the one non-obvious path rule

`database.env` must live at `domains/careers.fprecioushomecare.com/database.env`
- a **sibling** of `public_python/`, `public_html/`, and `frontend/` - **not**
inside `public_python/`.

Why: `backend/config.py` resolves the env file's path as *two directories
up* from itself. Locally that's `<repo root>/database.env` (`config.py`
sits in `backend/`, two levels up is the repo root, sibling to
`frontend/`). In this deployment's flattened layout, `config.py` sits
directly in `public_python/` (no nested `backend/` folder - see "Why the
layout looks like this" below), so two levels up lands one folder above
`public_python/`, at `domains/careers.fprecioushomecare.com/`. Put it
anywhere else and the app silently falls back to a local SQLite file
instead of erroring - which is exactly what happened the first time this
was deployed (see step 5's `SQLiteImpl` check above).

Contents should mirror local `database.env`, except:
- `DATABASE_URL`'s host is `localhost` (running on the DB server itself
  now, not connecting remotely)
- `MICROSOFT_REDIRECT_URI` and `CALENDAR_FRONTEND_REDIRECT_URL` point at
  `careers.fprecioushomecare.com`, not `localhost`
- `FRONTEND_BASE_URL=https://careers.fprecioushomecare.com` (this one
  doesn't exist in local `database.env` at all - it silently uses
  `config.py`'s `localhost:5173` fallback there. In production it's what
  gets embedded in candidate-facing application emails, so it must be set
  explicitly.)

If `MICROSOFT_REDIRECT_URI` ever changes, it also needs to be added to the
Entra ID app registration's Authentication page as a Web redirect URI -
that's a separate, manual step outside DirectAdmin entirely.

- `FORCE_HTTPS=true` — not present in local `database.env` at all (defaults
  to off there). Turns on app.py's HTTP→HTTPS redirect. **Verify it actually
  works after setting it and restarting** —
  `curl -sI http://careers.fprecioushomecare.com` should come back with a
  `302` to an `https://` URL. If it doesn't (still loads plainly over
  HTTP), that almost certainly means Apache isn't forwarding an
  `X-Forwarded-Proto` header to Passenger - the redirect is deliberately
  built to stay a no-op rather than guess in that case (a false positive
  would redirect-loop the whole site), so nothing breaks, it just means
  this particular fix isn't doing anything yet. Check DirectAdmin's SSL
  Certificates page for that domain for a built-in "Force HTTPS"/redirect
  option instead - if one exists, it handles this at the Apache level
  directly and doesn't depend on `FORCE_HTTPS` at all.

## Why the layout looks like this

DirectAdmin's Application root expects its startup file
(`wsgi_entry.py`) sitting directly inside it - so `public_python/` holds
`backend/`'s contents directly, not a nested `backend/` subfolder.
`app.py`'s `_FRONTEND_DIST` constant and `config.py`'s `database.env`
lookup both resolve "two directories up from this file" as the shared
project root, which is why `frontend/` and `database.env` both need to
sit as siblings of `public_python/` rather than inside it - that math
works out the same way whether the "root" is the actual repo root (local
dev) or `domains/careers.fprecioushomecare.com/` (this flattened
deployment).

## One-off admin scripts

`backend/deploy_create_admin.py` creates a single admin `User` (reads
`ADMIN_EMAIL`/`ADMIN_PASSWORD`/`ADMIN_FIRST_NAME`/`ADMIN_LAST_NAME` from
the Python App's Environment Variables, since the interactive
`flask create-user` CLI command doesn't work through DirectAdmin's
non-interactive script runner). To create another admin later: set those
four env vars, run the script the same way as migrations, then **delete
`ADMIN_PASSWORD` from Environment Variables afterward** - no reason to
leave a real password sitting there once the account exists.

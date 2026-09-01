#!/usr/bin/env bash
# Builds hiringTool-deploy.zip for manual deployment to HostPinnacle's
# DirectAdmin Python App (see DEPLOYMENT.md for the full runbook - this
# script only produces the zip, it doesn't upload or extract anything).
#
# Layout matters here and isn't arbitrary - see DEPLOYMENT.md's "Why the
# layout looks like this" section:
#   public_python/   <- backend/'s contents directly (no wrapping folder),
#                       since DirectAdmin's Python App expects its startup
#                       file (wsgi_entry.py) sitting at the app root.
#   frontend/        <- frontend/'s contents including a fresh dist/ build,
#                       as a SIBLING of public_python/ (config.py's and
#                       app.py's path math both resolve "two directories up
#                       from this file" as the shared root either locally
#                       or in this flattened server layout - see their
#                       comments).
#
# Usage: scripts/build_deploy_package.sh [output_path]
#   output_path defaults to ~/Desktop/hiringTool-deploy.zip - override if
#   you don't want it dropped on the Desktop, e.g. for a CI environment.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$HOME/Desktop/hiringTool-deploy.zip}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cd "$REPO_ROOT"

echo "==> Rebuilding frontend with a production-safe (relative) API URL..."
# VITE_API_URL must be empty in production: frontend and backend are
# same-origin there (Flask serves the built frontend directly - see
# app.py's serve_frontend()), so requests should go to relative paths like
# /api/apply, not a hardcoded http://127.0.0.1:5050 baked in at build time.
# This intentionally does NOT touch frontend/.env, which stays pointed at
# localhost for local dev.
(cd frontend && VITE_API_URL= npm run build)

echo "==> Staging public_python/ (from backend/)..."
mkdir -p "$STAGE/public_python" "$STAGE/frontend"
rsync -a \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='hiringtool_dev.db' \
  --exclude='uploads/' \
  --exclude='migration.sql' \
  backend/ "$STAGE/public_python/"

echo "==> Staging frontend/ (from frontend/, including the fresh dist/)..."
rsync -a \
  --exclude='node_modules' \
  --exclude='.vite' \
  --exclude='.env' \
  --exclude='hiringtool_dev.db' \
  frontend/ "$STAGE/frontend/"

find "$STAGE" -name '.DS_Store' -delete

# Sanity checks - fail loudly rather than shipping a broken package.
if [ ! -f "$STAGE/public_python/wsgi_entry.py" ]; then
  echo "ERROR: wsgi_entry.py missing from staged public_python/ - aborting." >&2
  exit 1
fi
if [ -f "$STAGE/public_python/passenger_wsgi.py" ]; then
  echo "ERROR: a passenger_wsgi.py ended up in public_python/ - this WILL" >&2
  echo "       collide with DirectAdmin's own auto-generated wrapper file" >&2
  echo "       of the same name. Aborting rather than shipping it." >&2
  exit 1
fi
if [ ! -f "$STAGE/frontend/dist/index.html" ]; then
  echo "ERROR: frontend/dist/index.html missing - the build above may have" >&2
  echo "       failed silently. Aborting." >&2
  exit 1
fi
if grep -rq "127.0.0.1:5050\|localhost:5050" "$STAGE/frontend/dist/assets/"*.js 2>/dev/null; then
  echo "ERROR: the built frontend still has a localhost API URL baked in -" >&2
  echo "       VITE_API_URL override didn't take. Aborting." >&2
  exit 1
fi

echo "==> Zipping to $OUT ..."
rm -f "$OUT"
(cd "$STAGE" && zip -rq "$OUT" public_python frontend)

echo "==> Done: $OUT ($(du -h "$OUT" | cut -f1))"
echo
echo "Next steps (see DEPLOYMENT.md for details):"
echo "  1. Upload $(basename "$OUT") into domains/careers.fprecioushomecare.com/ via File Manager"
echo "  2. Extract it there with 'Merge and overwrite' checked"
echo "  3. In the Python App page: Run Pip Install (if requirements.txt changed)"
echo "  4. Execute python script: public_python/deploy_run_migrations.py (if there are new migrations)"
echo "  5. Restart the app (see DEPLOYMENT.md - Passenger won't pick up new code otherwise)"

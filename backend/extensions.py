"""Flask extension instances that need to exist at import time, before
create_app() runs - route modules (e.g. routes/apply.py) decorate their view
functions with @limiter.limit(...) at import time, which happens when app.py
does `from routes.apply import apply_bp`, before create_app() has an app to
bind to. Instantiating here (with no app) and binding later via
limiter.init_app(app) inside create_app() is the standard Flask-Limiter
"deferred init" pattern - the same reason models.py's `db` is a
module-level SQLAlchemy() instead of being constructed inside create_app().
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Per-IP is the default key for every limit unless a route overrides
# key_func on a specific @limiter.limit(...) call (see routes/apply.py's
# per-email-per-job limit). Storage backend is configured via
# RATELIMIT_STORAGE_URI (see config.py) - defaults to in-memory, which is
# fine for local dev/tests but does NOT share state across multiple worker
# processes; point it at Redis for any real deployment.
limiter = Limiter(key_func=get_remote_address)

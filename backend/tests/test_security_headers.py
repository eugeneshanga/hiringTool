"""The app-wide security response headers set in app.py's _security_headers
after_request hook: X-Content-Type-Options and Content-Security-Policy."""
import tempfile

from app import create_app


def _client(**overrides):
    with tempfile.TemporaryDirectory() as upload_dir:
        app = create_app({
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'TESTING': True,
            'UPLOAD_FOLDER': upload_dir,
            'SCHEDULER_ENABLED': False,
            **overrides,
        })
        return app.test_client()


def test_nosniff_on_every_response(client):
    assert client.get('/api/health').headers['X-Content-Type-Options'] == 'nosniff'
    # 404s go through after_request too.
    assert client.get('/api/nope').headers['X-Content-Type-Options'] == 'nosniff'


def test_csp_is_report_only_by_default(client):
    resp = client.get('/api/health')
    assert 'Content-Security-Policy-Report-Only' in resp.headers
    assert 'Content-Security-Policy' not in resp.headers
    assert "script-src 'self'" in resp.headers['Content-Security-Policy-Report-Only']


def test_csp_enforces_when_report_only_is_off():
    resp = _client(CSP_REPORT_ONLY=False).get('/api/health')
    assert 'Content-Security-Policy' in resp.headers
    assert 'Content-Security-Policy-Report-Only' not in resp.headers


def test_csp_key_directives_present(client):
    csp = client.get('/api/health').headers['Content-Security-Policy-Report-Only']
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
    ):
        assert directive in csp
    # no escape hatches
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_csp_header_omitted_when_blank():
    resp = _client(CONTENT_SECURITY_POLICY='').get('/api/health')
    assert 'Content-Security-Policy' not in resp.headers
    assert 'Content-Security-Policy-Report-Only' not in resp.headers


def test_csp_also_set_on_the_spa_index(client):
    # The catch-all frontend route (serves index.html) runs through
    # after_request as well - the policy has to reach the actual HTML page,
    # not just the API.
    resp = client.get('/')
    assert 'Content-Security-Policy-Report-Only' in resp.headers

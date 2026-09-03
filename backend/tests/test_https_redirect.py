"""app.py's before_request HTTP->HTTPS redirect - off by default (so local
dev over plain http://localhost isn't affected), and even when enabled,
only ever acts on an explicit X-Forwarded-Proto: http from the proxy rather
than guessing, since a false positive would redirect-loop the whole site."""


def test_no_redirect_when_force_https_is_off(client):
    resp = client.get('/api/health', headers={'X-Forwarded-Proto': 'http'})
    assert resp.status_code == 200


def test_redirects_to_https_when_forwarded_proto_is_http(app, client):
    app.config['FORCE_HTTPS'] = True
    resp = client.get('/api/health', headers={'X-Forwarded-Proto': 'http'})
    assert resp.status_code == 302
    assert resp.headers['Location'].startswith('https://')


def test_no_redirect_when_forwarded_proto_is_already_https(app, client):
    app.config['FORCE_HTTPS'] = True
    resp = client.get('/api/health', headers={'X-Forwarded-Proto': 'https'})
    assert resp.status_code == 200


def test_no_redirect_when_forwarded_proto_header_is_missing(app, client):
    """The safety property this test is really pinning down: no header at
    all means "we don't know", and this must never guess - it stays a
    no-op rather than risk looping a request that's actually already
    HTTPS but whose proxy just isn't forwarding the header."""
    app.config['FORCE_HTTPS'] = True
    resp = client.get('/api/health')
    assert resp.status_code == 200

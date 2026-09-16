"""GET /api/candidates ordering - a "stack" (last in on top), not the
DB's default insertion order (which put the oldest candidate on top)."""
from datetime import datetime, timedelta


def test_candidates_are_listed_newest_first(client, auth_headers, candidate_factory):
    oldest = candidate_factory(name='Oldest', email='oldest@example.com',
                                created_at=datetime.utcnow() - timedelta(days=2))
    middle = candidate_factory(name='Middle', email='middle@example.com',
                                created_at=datetime.utcnow() - timedelta(days=1))
    newest = candidate_factory(name='Newest', email='newest@example.com',
                                created_at=datetime.utcnow())

    resp = client.get('/api/candidates', headers=auth_headers)
    ids = [c['id'] for c in resp.get_json()]

    assert ids.index(newest.id) < ids.index(middle.id) < ids.index(oldest.id)

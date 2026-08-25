"""GET /api/organization/interviewers - the stage editor's "who checks this
calendar" picker (see MeetingStageTemplate.interviewer_user_id). Deliberately
NOT admin-gated like GET /api/organization/users - any recruiter building out
a job's stages needs this, and it returns a much smaller shape (id/name
only) precisely so that's safe.
"""
from models import User, db


def test_available_to_a_plain_recruiter(client, auth_headers, user):
    # conftest's `user` fixture is role='recruiter', not admin - this proves
    # the route isn't gated the way GET /api/organization/users is.
    resp = client.get('/api/organization/interviewers', headers=auth_headers)

    assert resp.status_code == 200
    assert resp.get_json() == [{"id": user.id, "name": user.name}]


def test_requires_auth(client):
    resp = client.get('/api/organization/interviewers')
    assert resp.status_code == 401


def test_excludes_inactive_users(app, client, auth_headers, user):
    # Captured before the block below, which commits and (since Flask-
    # SQLAlchemy's scoped session is shared across app-context blocks in the
    # same test) would otherwise expire `user`'s already-loaded attributes,
    # leaving them inaccessible once we're back outside any app context.
    active_user_id = user.id

    with app.app_context():
        inactive = User(
            first_name='Inactive', last_name='Person', email='inactive@example.com', role='recruiter',
            is_active=False,
        )
        inactive.set_password('password123')
        db.session.add(inactive)
        db.session.commit()
        inactive_id = inactive.id

    resp = client.get('/api/organization/interviewers', headers=auth_headers)

    assert resp.status_code == 200
    ids = [row['id'] for row in resp.get_json()]
    assert active_user_id in ids
    assert inactive_id not in ids

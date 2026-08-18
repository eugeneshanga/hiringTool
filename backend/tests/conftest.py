import pytest
from flask_jwt_extended import create_access_token

from app import create_app
from models import Candidate, CandidateAccount, Job, MeetingStageTemplate, User, db


@pytest.fixture
def app():
    """A fresh app per test, backed by an in-memory SQLite DB — never touches
    the real dev DB. db.create_all() (not Alembic) is intentional here: tests
    want the schema built straight from models.py, not routed through
    migration history."""
    flask_app = create_app({
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'TESTING': True,
        'JWT_SECRET_KEY': 'test-secret',
    })
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    with app.app_context():
        u = User(first_name='Test', last_name='User', email='test@example.com', role='recruiter')
        u.set_password('password123')
        db.session.add(u)
        db.session.commit()
        db.session.refresh(u)
        return u


@pytest.fixture
def auth_headers(app, user):
    with app.app_context():
        token = create_access_token(identity=str(user.id), additional_claims={'account_type': 'user'})
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def candidate_account(app):
    with app.app_context():
        a = CandidateAccount(first_name='Cand', last_name='Idate', email='cand@example.com')
        a.set_password('password123')
        db.session.add(a)
        db.session.commit()
        db.session.refresh(a)
        return a


@pytest.fixture
def candidate_auth_headers(app, candidate_account):
    with app.app_context():
        token = create_access_token(
            identity=str(candidate_account.id), additional_claims={'account_type': 'candidate'}
        )
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def job(app):
    with app.app_context():
        j = Job(title='CHHA', status='Published')
        db.session.add(j)
        db.session.commit()
        db.session.refresh(j)
        return j


@pytest.fixture
def meeting_stage(app, job):
    with app.app_context():
        t = MeetingStageTemplate(
            job_id=job.id, meeting_type='Virtual interview', stage_name='CHHA Interview',
            duration_minutes=20, sort_order=0,
        )
        db.session.add(t)
        db.session.commit()
        db.session.refresh(t)
        return t


@pytest.fixture
def candidate_factory(app):
    def _make(**overrides):
        defaults = dict(name='Test Candidate', email='candidate@example.com')
        defaults.update(overrides)
        with app.app_context():
            c = Candidate(**defaults)
            db.session.add(c)
            db.session.commit()
            db.session.refresh(c)
            return c
    return _make

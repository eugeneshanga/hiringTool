"""routes/public.py - the unauthenticated careers landing page endpoints:
organization name/logo and the list of Published jobs. Distinct from
apply.py's get_public_job (a single job, by id, once a candidate already
has a link to it) - these are what a first-time visitor to '/' sees before
picking a job at all.
"""
from file_storage import organization_file_path
from models import Job, Organization, db


# --- GET /api/public/organization -------------------------------------------

def test_get_public_organization_returns_fallback_name_when_unset(client):
    resp = client.get('/api/public/organization')

    assert resp.status_code == 200
    assert resp.get_json() == {"name": "this organization", "has_logo": False}


def test_get_public_organization_returns_real_name_and_has_logo(app, client):
    with app.app_context():
        db.session.add(Organization(name='Florence Precious Home Care', logo_stored_filename='abc_logo.png'))
        db.session.commit()

    resp = client.get('/api/public/organization')

    assert resp.status_code == 200
    assert resp.get_json() == {"name": "Florence Precious Home Care", "has_logo": True}


# --- GET /api/public/organization/logo --------------------------------------

def test_get_public_organization_logo_404s_when_none_uploaded(client):
    resp = client.get('/api/public/organization/logo')
    assert resp.status_code == 404


def test_get_public_organization_logo_serves_the_file(app, client):
    with app.app_context():
        stored_filename = 'abc123_logo.png'
        with open(organization_file_path(stored_filename), 'wb') as f:
            f.write(b'fake-png-bytes')
        db.session.add(Organization(
            name='Florence Precious Home Care',
            logo_original_filename='logo.png', logo_stored_filename=stored_filename,
        ))
        db.session.commit()

    resp = client.get('/api/public/organization/logo')

    assert resp.status_code == 200
    assert resp.data == b'fake-png-bytes'


# --- GET /api/public/jobs ----------------------------------------------------

def test_list_public_jobs_only_includes_published(app, client):
    with app.app_context():
        db.session.add_all([
            Job(title='Published Job', status='Published'),
            Job(title='Draft Job', status='Draft'),
            Job(title='Closed Job', status='Closed'),
        ])
        db.session.commit()

    resp = client.get('/api/public/jobs')

    assert resp.status_code == 200
    titles = [j['title'] for j in resp.get_json()]
    assert titles == ['Published Job']


def test_list_public_jobs_shape_and_newest_first(app, client):
    with app.app_context():
        older = Job(
            title='CHHA', status='Published', city='Elizabethtown', state='KY',
            job_type=['Full-time'], min_salary=15.0, max_salary=18.0, salary_period='Hourly',
        )
        db.session.add(older)
        db.session.commit()
        newer = Job(title='LPN', status='Published')
        db.session.add(newer)
        db.session.commit()

    resp = client.get('/api/public/jobs')

    assert resp.status_code == 200
    data = resp.get_json()
    assert [j['title'] for j in data] == ['LPN', 'CHHA']
    chha = data[1]
    assert chha['location'] == 'Elizabethtown, KY'
    assert chha['job_type'] == ['Full-time']
    assert chha['min_salary'] == 15.0
    assert chha['max_salary'] == 18.0
    assert chha['salary_period'] == 'Hourly'
    # Hand-picked public contract, not Job.to_dict() - no recruiter-only
    # fields like candidate_count leak through.
    assert 'candidate_count' not in chha

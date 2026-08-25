"""POST /api/apply, its anti-abuse checks, and the "schedule your interview"
email it sends on a real application. No calendar involved yet (see
routes/apply.py's module docstring). Real DNS/email are never hit here - the
MX check is monkeypatched to "has MX" by default (mock_mx_lookup below) and
overridden per-test where the MX-failure path itself is under test; the
email send is replaced with a spy (mock_email below) so tests can assert
whether it was called without depending on email_sender.py's own behavior
(see test_email_sender.py for that).

multipart/form-data, not JSON - the endpoint carries a resume upload, so
every request here goes through client.post(..., data=_payload(...)),
never json=. UPLOAD_FOLDER is pointed at a throwaway temp dir by conftest.py's
`app` fixture, so these never touch backend/uploads/.
"""
import io
from datetime import datetime, timedelta

import pytest

import routes.apply as apply_module
from models import BlocklistEntry, Candidate, Job, db


@pytest.fixture(autouse=True)
def mock_mx_lookup(monkeypatch):
    monkeypatch.setattr(apply_module, '_email_domain_has_mx', lambda email: True)


@pytest.fixture(autouse=True)
def mock_email(monkeypatch):
    calls = []
    monkeypatch.setattr(
        apply_module, 'send_schedule_interview_email', lambda **kwargs: calls.append(kwargs) or True
    )
    return calls


def _resume_file(name='resume.pdf'):
    return (io.BytesIO(b'%PDF-1.4 fake resume content'), name)


def _payload(**overrides):
    """Builds the multipart form dict. An override of None drops the key
    entirely (e.g. resume=None means "no file was attached", not a literal
    null value for Werkzeug's multipart encoder to choke on)."""
    defaults = {
        'first_name': 'Jane',
        'last_name': 'Applicant',
        'email': 'jane@example.com',
        'work_authorized': 'yes',
        'requires_visa_sponsorship': 'no',
        'resume': _resume_file(),
    }
    defaults.update(overrides)
    return {k: v for k, v in defaults.items() if v is not None}


def _post_apply(client, **overrides):
    return client.post('/api/apply', data=_payload(**overrides), content_type='multipart/form-data')


# --- happy path -------------------------------------------------------------

def test_creates_candidate_with_no_account_and_a_live_application_token(app, client, job, mock_email):
    resp = _post_apply(
        client, email='Jane@Example.com', phone='555-1234', job_id=job.id,
        address_line1='123 Main St', city='Springfield', state='IL', postal_code='62704',
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}

    with app.app_context():
        candidate = Candidate.query.filter_by(job_id=job.id).first()
        assert candidate is not None
        assert candidate.name == 'Jane Applicant'  # first_name + last_name combined
        assert candidate.email == 'jane@example.com'  # normalized to lowercase
        assert candidate.candidate_account_id is None
        assert candidate.address_line1 == '123 Main St'
        assert candidate.city == 'Springfield'
        assert candidate.state == 'IL'
        assert candidate.postal_code == '62704'
        assert candidate.work_authorized is True
        assert candidate.requires_visa_sponsorship is False
        assert candidate.resume_stored_filename is not None
        assert candidate.resume_original_filename == 'resume.pdf'
        assert candidate.application_token is not None
        assert len(candidate.application_token) == 64
        assert candidate.application_token_expires_at > datetime.utcnow()
        token = candidate.application_token

    assert len(mock_email) == 1
    assert mock_email[0]['to_email'] == 'jane@example.com'
    assert mock_email[0]['apply_url'].endswith(f"/apply/schedule/{token}")


# --- validation (real errors - not abuse signals) ----------------------------

def test_requires_first_last_name_email_and_job_id(client):
    resp = client.post('/api/apply', data={}, content_type='multipart/form-data')
    assert resp.status_code == 400


def test_rejects_malformed_email(client, job):
    resp = _post_apply(client, email='not-an-email', job_id=job.id)
    assert resp.status_code == 400


def test_requires_a_resume(client, job):
    resp = _post_apply(client, job_id=job.id, resume=None)
    assert resp.status_code == 400
    with client.application.app_context():
        assert Candidate.query.filter_by(job_id=job.id).first() is None


def test_rejects_a_resume_over_the_size_cap(client, job):
    """App-wide MAX_CONTENT_LENGTH (config.py, 15MB) - enforced by Werkzeug
    before the view even runs, so this exercises app.py's 413 handler
    (a JSON error, matching every other error response) rather than
    anything in routes/apply.py itself."""
    oversized = io.BytesIO(b'0' * (16 * 1024 * 1024))
    resp = _post_apply(client, job_id=job.id, resume=(oversized, 'huge-resume.pdf'))

    assert resp.status_code == 413
    assert 'too large' in resp.get_json()['error']
    with client.application.app_context():
        assert Candidate.query.filter_by(job_id=job.id).first() is None


def test_requires_answers_to_both_work_authorization_questions(client, job):
    # Different emails per call - same email+job is rate-limited to 1/day
    # (see the rate-limiting tests below), which would otherwise mask the
    # validation error under test with a 429 on the second call.
    resp = _post_apply(client, email='a@example.com', job_id=job.id, work_authorized='')
    assert resp.status_code == 400

    resp = _post_apply(client, email='b@example.com', job_id=job.id, requires_visa_sponsorship='maybe')
    assert resp.status_code == 400


def test_rejects_unpublished_job(app, client):
    with app.app_context():
        draft = Job(title='Draft Job', status='Draft')
        db.session.add(draft)
        db.session.commit()
        draft_job_id = draft.id

    resp = _post_apply(client, job_id=draft_job_id)
    assert resp.status_code == 400


def test_rejects_nonexistent_job(client):
    resp = _post_apply(client, job_id=999999)
    assert resp.status_code == 400


# --- MX check -----------------------------------------------------------------

def test_rejects_email_domain_with_no_mx_record(client, job, monkeypatch, mock_email):
    monkeypatch.setattr(apply_module, '_email_domain_has_mx', lambda email: False)

    resp = _post_apply(client, email='nobody@no-mx.example', job_id=job.id)

    assert resp.status_code == 400
    with client.application.app_context():
        assert Candidate.query.filter_by(email='nobody@no-mx.example').first() is None
    assert mock_email == []


# --- blocklist ------------------------------------------------------------

def test_blocklisted_email_is_rejected(app, client, job, mock_email):
    with app.app_context():
        db.session.add(BlocklistEntry(entry_type='email', value='blocked@example.com'))
        db.session.commit()

    resp = _post_apply(client, email='blocked@example.com', job_id=job.id)

    assert resp.status_code == 403
    with app.app_context():
        assert Candidate.query.filter_by(email='blocked@example.com').first() is None
    assert mock_email == []


# --- honeypot -----------------------------------------------------------------

def test_honeypot_field_looks_like_success_but_creates_nothing(app, client, job, mock_email):
    resp = _post_apply(client, email='bot@example.com', job_id=job.id, website='http://spam.example')

    # Same response shape as a real success - a bot can't tell it was dropped.
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
    with app.app_context():
        assert Candidate.query.filter_by(email='bot@example.com').first() is None
    assert mock_email == []


# --- dedupe -------------------------------------------------------------------

def test_dedupe_no_ops_when_a_live_application_already_exists(app, client, job, mock_email):
    with app.app_context():
        existing = Candidate(
            name='Jane Applicant', email='jane@example.com', job_id=job.id,
            application_token='existing-token', application_token_expires_at=datetime.utcnow() + timedelta(days=5),
        )
        db.session.add(existing)
        db.session.commit()

    resp = _post_apply(client, job_id=job.id)

    assert resp.status_code == 200
    with app.app_context():
        candidates = Candidate.query.filter_by(job_id=job.id, email='jane@example.com').all()
        assert len(candidates) == 1
        assert candidates[0].application_token == 'existing-token'  # untouched, not regenerated
    assert mock_email == []  # no second email for a no-op


def test_reapplies_after_the_previous_token_has_expired(app, client, job):
    with app.app_context():
        expired = Candidate(
            name='Jane Applicant', email='jane@example.com', job_id=job.id,
            application_token='expired-token', application_token_expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(expired)
        db.session.commit()

    resp = _post_apply(client, job_id=job.id)

    assert resp.status_code == 200
    with app.app_context():
        candidates = Candidate.query.filter_by(job_id=job.id, email='jane@example.com').all()
        assert len(candidates) == 2
        new_candidate = next(c for c in candidates if c.application_token != 'expired-token')
        assert new_candidate.application_token_expires_at > datetime.utcnow()


# --- email delivery is best-effort ---------------------------------------------

def test_email_send_failure_does_not_fail_the_request(app, client, job, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("provider is down")

    monkeypatch.setattr(apply_module, 'send_schedule_interview_email', _boom)

    resp = _post_apply(client, email='jane@example.com', job_id=job.id)

    # The candidate was still created - a notification failure doesn't undo
    # the write or surface as a 500 to the applicant.
    assert resp.status_code == 200
    with app.app_context():
        assert Candidate.query.filter_by(email='jane@example.com', job_id=job.id).first() is not None


# --- resume save is best-effort, like email ------------------------------------

def test_resume_save_failure_does_not_fail_the_request(app, client, job, monkeypatch):
    monkeypatch.setattr(
        apply_module, 'save_candidate_file',
        lambda candidate_id, file_storage: (_ for _ in ()).throw(RuntimeError("disk is full")),
    )

    resp = _post_apply(client, email='jane@example.com', job_id=job.id)

    assert resp.status_code == 200
    with app.app_context():
        candidate = Candidate.query.filter_by(email='jane@example.com', job_id=job.id).first()
        assert candidate is not None
        assert candidate.resume_stored_filename is None


# --- rate limiting --------------------------------------------------------------

def test_rate_limits_repeat_submissions_for_the_same_email_and_job(client, job):
    assert _post_apply(client, email='repeat@example.com', job_id=job.id).status_code == 200
    resp = _post_apply(client, email='repeat@example.com', job_id=job.id)

    assert resp.status_code == 429


def test_rate_limits_by_ip_across_different_applicants(client, job):
    for i in range(5):
        resp = _post_apply(client, email=f'person{i}@example.com', job_id=job.id)
        assert resp.status_code == 200

    resp = _post_apply(client, email='person5@example.com', job_id=job.id)

    assert resp.status_code == 429


# --- public job info (for the apply form) --------------------------------------

def test_public_job_returns_minimal_info_for_published_jobs(app, client, job):
    with app.app_context():
        from models import Organization
        db.session.add(Organization(name='Florence Precious Home Care'))
        db.session.commit()

    resp = client.get(f'/api/apply/jobs/{job.id}')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {
        "id": job.id, "title": job.title, "location": job.location,
        "description": job.description, "highlights": job.highlights or [],
        "job_type": job.job_type or [], "min_salary": job.min_salary,
        "max_salary": job.max_salary, "salary_period": job.salary_period,
        "organization_name": "Florence Precious Home Care",
    }


def test_public_job_falls_back_to_a_generic_name_if_organization_is_unset(client, job):
    resp = client.get(f'/api/apply/jobs/{job.id}')

    assert resp.status_code == 200
    assert resp.get_json()['organization_name'] == 'this organization'


def test_public_job_404s_for_a_draft_job(app, client):
    with app.app_context():
        draft = Job(title='Draft Job', status='Draft')
        db.session.add(draft)
        db.session.commit()
        draft_id = draft.id

    resp = client.get(f'/api/apply/jobs/{draft_id}')

    assert resp.status_code == 404


def test_public_job_404s_for_an_unknown_job(client):
    resp = client.get('/api/apply/jobs/999999')
    assert resp.status_code == 404

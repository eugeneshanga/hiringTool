"""upload_validation.reject_bad_upload and the routes that use it. The
security point: a candidate must not be able to upload a file that a
browser will execute as markup (stored XSS when a recruiter opens it) -
covered here for the public apply form (routes/apply.py) and the
recruiter-side resume upload (routes/candidates.py). routes/status.py's
onboarding upload has its own coverage in test_status.py."""
import io
import zipfile

import pytest

from upload_validation import (
    ONBOARDING_EXTENSIONS,
    RESUME_EXTENSIONS,
    reject_bad_upload,
)


class _FakeUpload:
    """Stands in for a Werkzeug FileStorage: a .filename and a .stream."""
    def __init__(self, filename, data):
        self.filename = filename
        self.stream = io.BytesIO(data)


def _pdf(data=b'%PDF-1.4 hello'):
    return data


def _docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('word/document.xml', '<xml/>')
    return buf.getvalue()


# --- reject_bad_upload unit -------------------------------------------------

def test_accepts_a_real_pdf():
    assert reject_bad_upload(
        _FakeUpload('resume.pdf', _pdf()), allowed_extensions=RESUME_EXTENSIONS, max_size_bytes=1_000
    ) is None


def test_accepts_a_real_docx():
    assert reject_bad_upload(
        _FakeUpload('resume.docx', _docx()), allowed_extensions=RESUME_EXTENSIONS, max_size_bytes=10_000
    ) is None


def test_rejects_a_disallowed_extension():
    err = reject_bad_upload(
        _FakeUpload('resume.html', b'<script>alert(1)</script>'),
        allowed_extensions=RESUME_EXTENSIONS, max_size_bytes=1_000,
    )
    assert err[1] == 400
    assert 'accepted' in err[0]['error']


def test_rejects_html_disguised_as_pdf():
    """The core stored-XSS defense: right extension, wrong content."""
    err = reject_bad_upload(
        _FakeUpload('resume.pdf', b'<!doctype html><script>steal()</script>'),
        allowed_extensions=RESUME_EXTENSIONS, max_size_bytes=1_000,
    )
    assert err[1] == 400
    assert "doesn't look like a valid PDF" in err[0]['error']


def test_rejects_a_zip_renamed_to_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('notes.txt', 'not a word doc')
    err = reject_bad_upload(
        _FakeUpload('resume.docx', buf.getvalue()),
        allowed_extensions=RESUME_EXTENSIONS, max_size_bytes=10_000,
    )
    assert err[1] == 400


def test_rejects_an_oversized_but_otherwise_valid_file():
    err = reject_bad_upload(
        _FakeUpload('resume.pdf', b'%PDF-1.4\n' + b'0' * 5_000),
        allowed_extensions=RESUME_EXTENSIONS, max_size_bytes=1_000,
    )
    assert err[1] == 400
    assert 'too large' in err[0]['error']


def test_onboarding_allowlist_includes_images_resume_does_not():
    assert '.png' in ONBOARDING_EXTENSIONS
    assert '.png' not in RESUME_EXTENSIONS


# --- public apply form ----------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_apply_deps(monkeypatch):
    import routes.apply as apply_module
    monkeypatch.setattr(apply_module, '_email_domain_has_mx', lambda email: True)
    monkeypatch.setattr(
        apply_module, 'send_schedule_interview_email', lambda **kwargs: True
    )


def _apply(client, job, resume):
    return client.post(
        '/api/apply',
        data={
            'first_name': 'Jane', 'last_name': 'Applicant', 'email': 'jane@example.com',
            'work_authorized': 'yes', 'requires_visa_sponsorship': 'no',
            'job_id': str(job.id), 'resume': resume,
        },
        content_type='multipart/form-data',
    )


def test_apply_rejects_an_html_resume(app, client, job):
    from models import Candidate
    resp = _apply(client, job, (io.BytesIO(b'<script>alert(document.cookie)</script>'), 'resume.html'))
    assert resp.status_code == 400
    with app.app_context():
        assert Candidate.query.filter_by(job_id=job.id).first() is None


def test_apply_rejects_html_disguised_as_pdf(app, client, job):
    from models import Candidate
    resp = _apply(client, job, (io.BytesIO(b'<!doctype html><script>x()</script>'), 'resume.pdf'))
    assert resp.status_code == 400
    with app.app_context():
        assert Candidate.query.filter_by(job_id=job.id).first() is None


def test_apply_accepts_a_real_pdf(app, client, job):
    resp = _apply(client, job, (io.BytesIO(b'%PDF-1.4 real'), 'resume.pdf'))
    assert resp.status_code == 200


# --- recruiter-side resume upload + download headers ---------------------

def test_recruiter_resume_upload_rejects_html(client, auth_headers, candidate_factory):
    c = candidate_factory()
    resp = client.post(
        f'/api/candidates/{c.id}/resume', headers=auth_headers,
        data={'file': (io.BytesIO(b'<script>evil()</script>'), 'resume.html')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 400


def test_resume_download_is_an_attachment_with_nosniff(client, auth_headers, candidate_factory):
    c = candidate_factory()
    client.post(
        f'/api/candidates/{c.id}/resume', headers=auth_headers,
        data={'file': (io.BytesIO(b'%PDF-1.4 real'), 'resume.pdf')},
        content_type='multipart/form-data',
    )
    resp = client.get(f'/api/candidates/{c.id}/resume', headers=auth_headers)
    assert resp.status_code == 200
    assert 'attachment' in resp.headers['Content-Disposition']
    assert resp.headers['X-Content-Type-Options'] == 'nosniff'

"""GET /api/status: public lookup of a booked interview by confirmation code
or phone number, including the onboarding document checklist. See
routes/status.py's module docstring for why phone lookups are scoped to only
interviews actually booked through the public apply flow
(Interview.confirmation_code IS NOT NULL), and for why there's no candidate
login - POST /api/status/documents (tested below) is how a candidate submits
onboarding documents instead, gated by the same code/phone check as the GET.
"""
import io
import zipfile
from datetime import datetime, timedelta

import pytest

from models import Candidate, CandidateDocument, Interview, Job, MeetingStageTemplate, OnboardingDocumentItem, db


def _book(app, job, *, phone='555-123-4567', confirmation_code='ABC234XYZ', scheduled_start=None, public=True):
    """Creates a Candidate + Interview as if booked (or not) through the
    public apply flow. public=False mimics a recruiter-created interview -
    no confirmation_code - to verify phone lookups never surface those."""
    scheduled_start = scheduled_start or (datetime.utcnow() + timedelta(days=2))
    with app.app_context():
        candidate = Candidate(name='Jane Applicant', email='jane@example.com', job_id=job.id, phone=phone)
        db.session.add(candidate)
        db.session.commit()

        interview = Interview(
            job_id=job.id, stage_name='Virtual interview', meeting_type='Interview',
            scheduled_start=scheduled_start, scheduled_end=scheduled_start + timedelta(minutes=20),
            confirmation_code=(confirmation_code if public else None),
            meeting_link='https://meet.google.com/abc-defg-hij',
        )
        interview.candidates.append(candidate)
        db.session.add(interview)
        db.session.commit()
        return candidate.id, interview.id


def test_requires_code_or_phone(client):
    resp = client.get('/api/status')
    assert resp.status_code == 400


def test_lookup_by_code_returns_booking_details(app, client, job):
    _book(app, job, confirmation_code='ABC234XYZ')

    resp = client.get('/api/status?code=ABC234XYZ')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['candidate_name'] == 'Jane Applicant'
    assert data['job_title'] == job.title
    assert data['stage_name'] == 'Virtual interview'
    assert data['meeting_link'] == 'https://meet.google.com/abc-defg-hij'
    assert data['confirmation_code'] == 'ABC234XYZ'


def test_lookup_by_unknown_code_returns_404(client):
    resp = client.get('/api/status?code=DOESNOTEXIST')
    assert resp.status_code == 404


def test_lookup_by_phone_normalizes_formatting(app, client, job):
    _book(app, job, phone='555-123-4567', confirmation_code='ABC234XYZ')

    resp = client.get('/api/status?phone=(555) 123-4567')

    assert resp.status_code == 200
    assert resp.get_json()['confirmation_code'] == 'ABC234XYZ'


def test_lookup_by_phone_with_country_code_prefix_matches(app, client, job):
    _book(app, job, phone='555-123-4567', confirmation_code='ABC234XYZ')

    resp = client.get('/api/status?phone=1-555-123-4567')

    assert resp.status_code == 200


def test_lookup_by_phone_never_surfaces_a_non_public_interview(app, client, job):
    _book(app, job, phone='555-999-0000', public=False)

    resp = client.get('/api/status?phone=555-999-0000')

    assert resp.status_code == 404


def test_lookup_by_too_short_phone_returns_404(client):
    resp = client.get('/api/status?phone=555')
    assert resp.status_code == 404


def test_lookup_by_phone_prefers_soonest_upcoming_booking(app, client, job):
    _book(
        app, job, phone='555-123-4567', confirmation_code='PAST234XY',
        scheduled_start=datetime.utcnow() - timedelta(days=10),
    )
    _book(
        app, job, phone='555-123-4567', confirmation_code='FUT234XYZ',
        scheduled_start=datetime.utcnow() + timedelta(days=3),
    )

    resp = client.get('/api/status?phone=555-123-4567')

    assert resp.status_code == 200
    assert resp.get_json()['confirmation_code'] == 'FUT234XYZ'


def test_rate_limits_repeat_lookups_by_ip(client):
    for _ in range(20):
        client.get('/api/status?code=nonexistent')

    resp = client.get('/api/status?code=nonexistent')

    assert resp.status_code == 429


def _add_onboarding_item(app, meeting_stage, **overrides):
    with app.app_context():
        defaults = dict(
            meeting_stage_template_id=meeting_stage.id, description='Upload your license',
            required=True, sort_order=0,
        )
        defaults.update(overrides)
        item = OnboardingDocumentItem(**defaults)
        db.session.add(item)
        db.session.commit()
        db.session.refresh(item)
        return item


def _pdf_bytes():
    return b'%PDF-1.4 fake pdf content'


def _docx_bytes():
    """A minimal real ZIP with the one path _looks_like_docx checks for -
    not a valid Word document, but a valid enough one for that check."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('word/document.xml', '<xml>fake docx</xml>')
    return buf.getvalue()


def _png_bytes():
    return b'\x89PNG\r\n\x1a\n' + b'0' * 20


# --- onboarding checklist on GET /api/status ---------------------------------

def test_status_includes_onboarding_checklist(app, client, job, meeting_stage):
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage, description='Upload your license')

    resp = client.get('/api/status?code=ABC234XYZ')

    assert resp.status_code == 200
    assert resp.get_json()['onboarding_documents'] == [{
        "item_id": item.id, "description": "Upload your license", "type": "file_upload",
        "required": True, "submission": None,
    }]


def test_status_onboarding_checklist_reflects_existing_submission(app, client, job, meeting_stage):
    candidate_id, _interview_id = _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)
    with app.app_context():
        db.session.add(CandidateDocument(
            candidate_id=candidate_id, onboarding_item_id=item.id,
            original_filename='license.pdf', stored_filename='fake_stored.pdf',
        ))
        db.session.commit()

    resp = client.get('/api/status?code=ABC234XYZ')

    submission = resp.get_json()['onboarding_documents'][0]['submission']
    assert submission is not None
    assert submission['original_filename'] == 'license.pdf'


def test_status_onboarding_checklist_empty_when_job_has_no_items(app, client, job):
    _book(app, job, confirmation_code='ABC234XYZ')

    resp = client.get('/api/status?code=ABC234XYZ')

    assert resp.get_json()['onboarding_documents'] == []


# --- POST /api/status/documents ----------------------------------------------

def test_upload_document_requires_code_or_phone(client):
    resp = client.post('/api/status/documents', data={}, content_type='multipart/form-data')
    assert resp.status_code == 400


def test_upload_document_404s_for_unknown_code(client):
    resp = client.post(
        '/api/status/documents',
        data={'code': 'NOPE', 'onboarding_item_id': '1', 'file': (io.BytesIO(_pdf_bytes()), 'license.pdf')},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 404


def test_upload_document_succeeds_with_a_pdf(app, client, job, meeting_stage):
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(_pdf_bytes()), 'license.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 200
    assert resp.get_json()['original_filename'] == 'license.pdf'
    with app.app_context():
        assert CandidateDocument.query.filter_by(onboarding_item_id=item.id).count() == 1


def test_upload_document_replaces_an_existing_submission(app, client, job, meeting_stage):
    candidate_id, _interview_id = _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)
    with app.app_context():
        db.session.add(CandidateDocument(
            candidate_id=candidate_id, onboarding_item_id=item.id,
            original_filename='old.pdf', stored_filename='old_stored.pdf',
        ))
        db.session.commit()

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(_pdf_bytes()), 'new.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 200
    with app.app_context():
        docs = CandidateDocument.query.filter_by(onboarding_item_id=item.id).all()
        assert len(docs) == 1  # replaced in place, not a second row
        assert docs[0].original_filename == 'new.pdf'


def test_upload_document_accepts_docx(app, client, job, meeting_stage):
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(_docx_bytes()), 'license.docx'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 200


def test_upload_document_accepts_png(app, client, job, meeting_stage):
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(_png_bytes()), 'license.png'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 200


def test_upload_document_rejects_disallowed_extension(app, client, job, meeting_stage):
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(b'#!/bin/sh\necho hi'), 'script.sh'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 400
    assert 'PDF' in resp.get_json()['error']


def test_upload_document_rejects_content_that_does_not_match_extension(app, client, job, meeting_stage):
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            # .pdf extension, but not actually PDF content - the magic-byte
            # check should catch this even though the extension is allowed
            # (a spoofed extension is exactly what this defends against).
            'file': (io.BytesIO(b'not actually a pdf'), 'license.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 400


def test_upload_document_rejects_a_zip_renamed_to_docx(app, client, job, meeting_stage):
    # A plain ZIP (no word/document.xml inside) shares docx's PK\x03\x04
    # signature - the deeper zipfile-contents check must catch what a bare
    # byte-signature match would miss.
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('not_a_word_doc.txt', 'just some other zip content')

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(buf.getvalue()), 'license.docx'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 400


def test_upload_document_rejects_oversized_file(app, client, job, meeting_stage, monkeypatch):
    import routes.status as status_module
    monkeypatch.setattr(status_module, 'MAX_UPLOAD_SIZE_BYTES', 10)
    _book(app, job, confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(_pdf_bytes()), 'license.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 400
    assert 'too large' in resp.get_json()['error']


def test_upload_document_rejects_item_from_a_different_job(app, client, job, meeting_stage):
    _book(app, job, confirmation_code='ABC234XYZ')
    with app.app_context():
        other_job = Job(title='LPN', status='Published')
        db.session.add(other_job)
        db.session.commit()
        other_stage = MeetingStageTemplate(
            job_id=other_job.id, meeting_type='Virtual interview', stage_name='LPN Interview',
            duration_minutes=20, sort_order=0,
        )
        db.session.add(other_stage)
        db.session.commit()
        other_item = OnboardingDocumentItem(
            meeting_stage_template_id=other_stage.id, description='Other job doc',
            required=True, sort_order=0,
        )
        db.session.add(other_item)
        db.session.commit()
        other_item_id = other_item.id

    resp = client.post(
        '/api/status/documents',
        data={
            'code': 'ABC234XYZ', 'onboarding_item_id': str(other_item_id),
            'file': (io.BytesIO(_pdf_bytes()), 'license.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 400


def test_upload_document_works_with_phone_lookup_too(app, client, job, meeting_stage):
    _book(app, job, phone='555-123-4567', confirmation_code='ABC234XYZ')
    item = _add_onboarding_item(app, meeting_stage)

    resp = client.post(
        '/api/status/documents',
        data={
            'phone': '555-123-4567', 'onboarding_item_id': str(item.id),
            'file': (io.BytesIO(_pdf_bytes()), 'license.pdf'),
        },
        content_type='multipart/form-data',
    )

    assert resp.status_code == 200


def test_upload_document_rate_limited(client):
    for _ in range(10):
        client.post(
            '/api/status/documents',
            data={'code': 'NOPE', 'onboarding_item_id': '1', 'file': (io.BytesIO(_pdf_bytes()), 'x.pdf')},
            content_type='multipart/form-data',
        )

    resp = client.post(
        '/api/status/documents',
        data={'code': 'NOPE', 'onboarding_item_id': '1', 'file': (io.BytesIO(_pdf_bytes()), 'x.pdf')},
        content_type='multipart/form-data',
    )

    assert resp.status_code == 429

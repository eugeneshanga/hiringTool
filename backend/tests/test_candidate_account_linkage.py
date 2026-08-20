"""Candidate.name/email/phone are a point-in-time snapshot taken when a
Candidate row is created; once linked to a CandidateAccount, that snapshot
is not the source of truth anymore — Candidate.display_name/display_email/
display_phone (and everything built on them: to_dict, to_detail_dict, the
enrolled-candidates list on Interview) read live from the account instead."""

from models import Candidate, CandidateAccount, db


def test_linked_candidate_reflects_live_account_changes(app, client, auth_headers, candidate_account):
    with app.app_context():
        linked = Candidate(
            candidate_account_id=candidate_account.id,
            name=candidate_account.name, email=candidate_account.email, phone=candidate_account.phone,
        )
        db.session.add(linked)
        db.session.commit()
        candidate_id = linked.id

    before = client.get(f'/api/candidates/{candidate_id}', headers=auth_headers).get_json()
    assert before['email'] == 'cand@example.com'

    # Mutate the account directly (no "edit my profile" route exists yet —
    # this exercises the live-read behavior at the model/API boundary
    # regardless of how the account row eventually gets updated).
    with app.app_context():
        account = db.session.get(CandidateAccount, candidate_account.id)
        account.email = 'newemail@example.com'
        account.first_name = 'Updated'
        db.session.commit()

    after = client.get(f'/api/candidates/{candidate_id}', headers=auth_headers).get_json()
    assert after['email'] == 'newemail@example.com'
    assert after['name'] == 'Updated Idate'

    detail = client.get(f'/api/candidates/{candidate_id}', headers=auth_headers).get_json()
    assert detail['email'] == 'newemail@example.com'


def test_patch_rejects_contact_field_edits_on_a_linked_candidate(app, client, auth_headers, candidate_account):
    with app.app_context():
        linked = Candidate(
            candidate_account_id=candidate_account.id,
            name=candidate_account.name, email=candidate_account.email, phone=candidate_account.phone,
        )
        db.session.add(linked)
        db.session.commit()
        candidate_id = linked.id

    resp = client.patch(f'/api/candidates/{candidate_id}', headers=auth_headers, json={'email': 'hijacked@example.com'})
    assert resp.status_code == 400
    assert 'account' in resp.get_json()['error']

    # the account's real email must be untouched
    unchanged = client.get(f'/api/candidates/{candidate_id}', headers=auth_headers).get_json()
    assert unchanged['email'] == 'cand@example.com'

    # non-contact fields on a linked candidate are still editable as normal
    resp = client.patch(f'/api/candidates/{candidate_id}', headers=auth_headers, json={'interviewer': 'Pat'})
    assert resp.status_code == 200
    assert resp.get_json()['interviewer'] == 'Pat'


def test_recruiter_added_candidate_is_unaffected(client, auth_headers, candidate_factory):
    """No candidate_account_id at all — this must keep behaving exactly as
    before: the local columns are the only source of truth."""
    candidate = candidate_factory(name='Hand Added', email='handadded@example.com', phone='555-0100')

    detail = client.get(f'/api/candidates/{candidate.id}', headers=auth_headers).get_json()
    assert detail['name'] == 'Hand Added'
    assert detail['email'] == 'handadded@example.com'
    assert detail['phone'] == '555-0100'
    assert detail['candidate_account_id'] is None


def test_interview_enrolled_candidates_list_shows_live_name(app, client, auth_headers, candidate_account):
    with app.app_context():
        linked = Candidate(
            candidate_account_id=candidate_account.id,
            name=candidate_account.name, email=candidate_account.email, phone=candidate_account.phone,
        )
        db.session.add(linked)
        db.session.commit()
        candidate_id = linked.id

    interview = client.post('/api/interviews', headers=auth_headers, json={
        'stage_name': 'Orientation', 'meeting_type': 'Orientation',
        'scheduled_start': '2026-09-01T13:00:00.000Z', 'scheduled_end': '2026-09-01T14:00:00.000Z',
    }).get_json()
    client.post(f"/api/interviews/{interview['id']}/enroll", headers=auth_headers, json={'candidate_id': candidate_id})

    with app.app_context():
        account = db.session.get(CandidateAccount, candidate_account.id)
        account.first_name = 'Renamed'
        db.session.commit()

    updated = client.get(f"/api/interviews/{interview['id']}", headers=auth_headers).get_json()
    assert updated['candidates'] == [{'id': candidate_id, 'name': 'Renamed Idate'}]

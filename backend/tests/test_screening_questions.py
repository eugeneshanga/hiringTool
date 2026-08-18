"""Screening questions are scoped to a meeting stage (Stage editor > Pre-screen),
not the job directly — a candidate's combined answer list is the union across
all of the job's stages (see Job.screening_questions in models.py)."""


def test_create_list_update_delete_question(client, auth_headers, job, meeting_stage):
    base = f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}/screening-questions'

    assert client.get(base, headers=auth_headers).get_json() == []

    r = client.post(base, headers=auth_headers, json={'question_text': 'Do you have a valid license?'})
    assert r.status_code == 201
    question = r.get_json()
    assert question['meeting_stage_template_id'] == meeting_stage.id

    listed = client.get(base, headers=auth_headers).get_json()
    assert len(listed) == 1

    r = client.patch(f"{base}/{question['id']}", headers=auth_headers, json={'question_text': 'Updated?'})
    assert r.status_code == 200
    assert r.get_json()['question_text'] == 'Updated?'

    assert client.delete(f"{base}/{question['id']}", headers=auth_headers).status_code == 204
    assert client.get(base, headers=auth_headers).get_json() == []


def test_create_question_requires_text(client, auth_headers, job, meeting_stage):
    resp = client.post(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}/screening-questions',
        headers=auth_headers, json={'question_text': '  '},
    )
    assert resp.status_code == 400


def test_questions_from_a_different_job_are_404(client, auth_headers, job, meeting_stage):
    other_job = client.post('/api/jobs', headers=auth_headers, json={'title': 'Other Job'}).get_json()
    resp = client.get(
        f"/api/jobs/{other_job['id']}/meeting-stages/{meeting_stage.id}/screening-questions", headers=auth_headers
    )
    assert resp.status_code == 404


def test_candidate_sees_questions_across_all_job_stages(client, auth_headers, job, meeting_stage, candidate_factory):
    second_stage = client.post(f'/api/jobs/{job.id}/meeting-stages', headers=auth_headers, json={
        'meeting_type': 'In-person orientation', 'stage_name': 'Orientation',
    }).get_json()

    client.post(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}/screening-questions',
        headers=auth_headers, json={'question_text': 'Stage 1 question'},
    )
    client.post(
        f"/api/jobs/{job.id}/meeting-stages/{second_stage['id']}/screening-questions",
        headers=auth_headers, json={'question_text': 'Stage 2 question'},
    )

    candidate = candidate_factory(job_id=job.id)
    detail = client.get(f'/api/candidates/{candidate.id}', headers=auth_headers).get_json()
    question_texts = {a['question_text'] for a in detail['screening_answers']}
    assert question_texts == {'Stage 1 question', 'Stage 2 question'}


def test_saving_answer_rejects_question_from_a_different_job(client, auth_headers, job, meeting_stage, candidate_factory):
    other_job = client.post('/api/jobs', headers=auth_headers, json={'title': 'Other Job'}).get_json()
    question = client.post(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}/screening-questions',
        headers=auth_headers, json={'question_text': 'Q?'},
    ).get_json()

    candidate = candidate_factory(job_id=other_job['id'])
    resp = client.put(
        f'/api/candidates/{candidate.id}/screening-answers', headers=auth_headers,
        json={'answers': [{'question_id': question['id'], 'answer_text': 'Yes'}]},
    )
    assert resp.status_code == 400


def test_create_question_with_label_and_answer_options(client, auth_headers, job, meeting_stage):
    resp = client.post(
        f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}/screening-questions',
        headers=auth_headers,
        json={
            'question_text': 'Do you have current and valid car insurance?',
            'question_label': 'Car insurance',
            'answer_options': ['No I do not have access to a car', 'Yes I have my own car with car insurance'],
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body['question_label'] == 'Car insurance'
    assert body['answer_options'] == ['No I do not have access to a car', 'Yes I have my own car with car insurance']
    assert body['qualified_answers'] == []


def test_set_qualified_answers_must_be_subset_of_options(client, auth_headers, job, meeting_stage):
    base = f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}/screening-questions'
    question = client.post(base, headers=auth_headers, json={
        'question_text': 'Q?', 'answer_options': ['Yes', 'No'],
    }).get_json()

    bad = client.patch(f"{base}/{question['id']}", headers=auth_headers, json={
        'question_text': 'Q?', 'qualified_answers': ['Maybe'],
    })
    assert bad.status_code == 400

    good = client.patch(f"{base}/{question['id']}", headers=auth_headers, json={
        'question_text': 'Q?', 'qualified_answers': ['Yes'],
    })
    assert good.status_code == 200
    assert good.get_json()['qualified_answers'] == ['Yes']


def test_update_qualified_answers_without_resending_options(client, auth_headers, job, meeting_stage):
    """The 'Select qualified answers' step only sends qualified_answers —
    validation must fall back to the question's already-saved options."""
    base = f'/api/jobs/{job.id}/meeting-stages/{meeting_stage.id}/screening-questions'
    question = client.post(base, headers=auth_headers, json={
        'question_text': 'Q?', 'answer_options': ['Yes', 'No'],
    }).get_json()

    resp = client.patch(f"{base}/{question['id']}", headers=auth_headers, json={
        'question_text': 'Q?', 'qualified_answers': ['Yes'],
    })
    assert resp.status_code == 200
    assert resp.get_json()['answer_options'] == ['Yes', 'No']
    assert resp.get_json()['qualified_answers'] == ['Yes']

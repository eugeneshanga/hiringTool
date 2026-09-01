CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> c0a51148829e

CREATE TABLE jobs (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    title VARCHAR(150) NOT NULL, 
    status VARCHAR(50), 
    job_type JSON, 
    city VARCHAR(120), 
    state VARCHAR(60), 
    postal_code VARCHAR(20), 
    country VARCHAR(60), 
    min_salary FLOAT, 
    max_salary FLOAT, 
    salary_period VARCHAR(20), 
    highlights JSON, 
    description TEXT, 
    created_at DATETIME, 
    PRIMARY KEY (id)
);

CREATE TABLE users (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    first_name VARCHAR(120) NOT NULL, 
    last_name VARCHAR(120) NOT NULL, 
    phone VARCHAR(20), 
    email VARCHAR(120) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    `role` VARCHAR(50), 
    is_active BOOL NOT NULL, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

CREATE TABLE candidates (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(120) NOT NULL, 
    email VARCHAR(120) NOT NULL, 
    phone VARCHAR(20), 
    job_id INTEGER, 
    stage VARCHAR(50), 
    status VARCHAR(50), 
    interviewer VARCHAR(120), 
    scheduled BOOL, 
    city VARCHAR(120), 
    state VARCHAR(60), 
    source VARCHAR(120), 
    resume_original_filename VARCHAR(255), 
    resume_stored_filename VARCHAR(255), 
    created_at DATETIME, 
    updated_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(job_id) REFERENCES jobs (id)
);

CREATE TABLE interviews (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    job_id INTEGER, 
    stage_name VARCHAR(100) NOT NULL, 
    meeting_type VARCHAR(50) NOT NULL, 
    location VARCHAR(255), 
    scheduled_start DATETIME NOT NULL, 
    scheduled_end DATETIME NOT NULL, 
    capacity INTEGER NOT NULL, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(job_id) REFERENCES jobs (id)
);

CREATE TABLE job_screening_questions (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    job_id INTEGER NOT NULL, 
    question_text VARCHAR(500) NOT NULL, 
    sort_order INTEGER NOT NULL, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(job_id) REFERENCES jobs (id)
);

CREATE TABLE meeting_stage_templates (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    job_id INTEGER NOT NULL, 
    meeting_type VARCHAR(50) NOT NULL, 
    stage_name VARCHAR(100) NOT NULL, 
    duration_minutes INTEGER, 
    sort_order INTEGER NOT NULL, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(job_id) REFERENCES jobs (id)
);

CREATE TABLE candidate_documents (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    candidate_id INTEGER NOT NULL, 
    doc_type VARCHAR(30) NOT NULL, 
    original_filename VARCHAR(255) NOT NULL, 
    stored_filename VARCHAR(255) NOT NULL, 
    uploaded_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
    CONSTRAINT uq_candidate_doctype UNIQUE (candidate_id, doc_type)
);

CREATE TABLE candidate_screening_answers (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    candidate_id INTEGER NOT NULL, 
    question_id INTEGER NOT NULL, 
    answer_text TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
    FOREIGN KEY(question_id) REFERENCES job_screening_questions (id), 
    CONSTRAINT uq_candidate_question UNIQUE (candidate_id, question_id)
);

CREATE TABLE candidate_stage_progress (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    candidate_id INTEGER NOT NULL, 
    meeting_stage_template_id INTEGER NOT NULL, 
    status VARCHAR(30) NOT NULL, 
    scheduled_at DATETIME, 
    location VARCHAR(255), 
    notes TEXT, 
    score_communication INTEGER, 
    score_energy INTEGER, 
    score_relevant_experience INTEGER, 
    updated_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
    FOREIGN KEY(meeting_stage_template_id) REFERENCES meeting_stage_templates (id), 
    CONSTRAINT uq_candidate_stage UNIQUE (candidate_id, meeting_stage_template_id)
);

CREATE TABLE interview_candidates (
    interview_id INTEGER NOT NULL, 
    candidate_id INTEGER NOT NULL, 
    PRIMARY KEY (interview_id, candidate_id), 
    FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
    FOREIGN KEY(interview_id) REFERENCES interviews (id)
);

INSERT INTO alembic_version (version_num) VALUES ('c0a51148829e');

-- Running upgrade c0a51148829e -> 8f8d57bef010

ALTER TABLE interviews ADD COLUMN meeting_stage_template_id INTEGER;

ALTER TABLE interviews ADD CONSTRAINT fk_interviews_meeting_stage_template_id FOREIGN KEY(meeting_stage_template_id) REFERENCES meeting_stage_templates (id);

UPDATE interviews
        SET meeting_stage_template_id = (
            SELECT id FROM meeting_stage_templates
            WHERE meeting_stage_templates.job_id = interviews.job_id
              AND meeting_stage_templates.stage_name = interviews.stage_name
        )
        WHERE interviews.job_id IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM meeting_stage_templates
            WHERE meeting_stage_templates.job_id = interviews.job_id
              AND meeting_stage_templates.stage_name = interviews.stage_name
          );

UPDATE alembic_version SET version_num='8f8d57bef010' WHERE alembic_version.version_num = 'c0a51148829e';

-- Running upgrade 8f8d57bef010 -> 213d189a3b5f

CREATE TABLE screening_questions (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    meeting_stage_template_id INTEGER NOT NULL, 
    question_text VARCHAR(500) NOT NULL, 
    sort_order INTEGER NOT NULL, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(meeting_stage_template_id) REFERENCES meeting_stage_templates (id)
);

DROP TABLE job_screening_questions;

DROP TABLE candidate_screening_answers;

CREATE TABLE candidate_screening_answers (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    candidate_id INTEGER NOT NULL, 
    question_id INTEGER NOT NULL, 
    answer_text TEXT, 
    PRIMARY KEY (id), 
    FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
    FOREIGN KEY(question_id) REFERENCES screening_questions (id), 
    CONSTRAINT uq_candidate_question UNIQUE (candidate_id, question_id)
);

UPDATE alembic_version SET version_num='213d189a3b5f' WHERE alembic_version.version_num = '8f8d57bef010';

-- Running upgrade 213d189a3b5f -> 4d7a3c52ce34

ALTER TABLE screening_questions ADD COLUMN question_label VARCHAR(200);

ALTER TABLE screening_questions ADD COLUMN answer_options JSON NOT NULL DEFAULT '[]';

ALTER TABLE screening_questions ADD COLUMN qualified_answers JSON NOT NULL DEFAULT '[]';

ALTER TABLE screening_questions ALTER COLUMN answer_options DROP DEFAULT;

ALTER TABLE screening_questions ALTER COLUMN qualified_answers DROP DEFAULT;

UPDATE alembic_version SET version_num='4d7a3c52ce34' WHERE alembic_version.version_num = '213d189a3b5f';

-- Running upgrade 4d7a3c52ce34 -> cf57f8e3d4ea

ALTER TABLE meeting_stage_templates ADD COLUMN scheduling_window_days INTEGER NOT NULL DEFAULT '7';

ALTER TABLE meeting_stage_templates ALTER COLUMN scheduling_window_days DROP DEFAULT;

UPDATE alembic_version SET version_num='cf57f8e3d4ea' WHERE alembic_version.version_num = '4d7a3c52ce34';

-- Running upgrade cf57f8e3d4ea -> 2a3b3e4fd385

CREATE TABLE candidate_accounts (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    first_name VARCHAR(120) NOT NULL, 
    last_name VARCHAR(120) NOT NULL, 
    phone VARCHAR(20), 
    email VARCHAR(120) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    is_active BOOL NOT NULL, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    UNIQUE (email)
);

UPDATE alembic_version SET version_num='2a3b3e4fd385' WHERE alembic_version.version_num = 'cf57f8e3d4ea';

-- Running upgrade 2a3b3e4fd385 -> 886509c441e4

ALTER TABLE candidates ADD COLUMN candidate_account_id INTEGER;

ALTER TABLE candidates ADD CONSTRAINT fk_candidates_candidate_account_id FOREIGN KEY(candidate_account_id) REFERENCES candidate_accounts (id);

UPDATE alembic_version SET version_num='886509c441e4' WHERE alembic_version.version_num = '2a3b3e4fd385';

-- Running upgrade 886509c441e4 -> 7015c570a199

CREATE TABLE calendar_connections (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    google_email VARCHAR(120) NOT NULL, 
    encrypted_refresh_token TEXT NOT NULL, 
    access_token TEXT, 
    token_expiry DATETIME, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    CONSTRAINT fk_calendar_connections_user_id FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (user_id)
);

UPDATE alembic_version SET version_num='7015c570a199' WHERE alembic_version.version_num = '886509c441e4';

-- Running upgrade 7015c570a199 -> 255ddfa8e439

ALTER TABLE meeting_stage_templates ADD COLUMN default_capacity INTEGER;

ALTER TABLE meeting_stage_templates ADD COLUMN location VARCHAR(255);

ALTER TABLE meeting_stage_templates ADD COLUMN instructions TEXT;

UPDATE alembic_version SET version_num='255ddfa8e439' WHERE alembic_version.version_num = '7015c570a199';

-- Running upgrade 255ddfa8e439 -> 9a1c2f7e5b3d

CREATE TABLE onboarding_document_items (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    meeting_stage_template_id INTEGER NOT NULL, 
    description VARCHAR(500) NOT NULL, 
    item_type VARCHAR(30) NOT NULL, 
    required BOOL NOT NULL, 
    sort_order INTEGER NOT NULL, 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(meeting_stage_template_id) REFERENCES meeting_stage_templates (id)
);

DROP TABLE candidate_documents;

CREATE TABLE candidate_documents (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    candidate_id INTEGER NOT NULL, 
    onboarding_item_id INTEGER NOT NULL, 
    original_filename VARCHAR(255) NOT NULL, 
    stored_filename VARCHAR(255) NOT NULL, 
    uploaded_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
    FOREIGN KEY(onboarding_item_id) REFERENCES onboarding_document_items (id), 
    CONSTRAINT uq_candidate_onboarding_item UNIQUE (candidate_id, onboarding_item_id)
);

UPDATE alembic_version SET version_num='9a1c2f7e5b3d' WHERE alembic_version.version_num = '255ddfa8e439';

-- Running upgrade 9a1c2f7e5b3d -> 6e2d4a9b7c1f

ALTER TABLE candidate_stage_progress ADD COLUMN cancellation_reason TEXT;

ALTER TABLE candidate_stage_progress ADD COLUMN prompt_reschedule BOOL;

UPDATE alembic_version SET version_num='6e2d4a9b7c1f' WHERE alembic_version.version_num = '9a1c2f7e5b3d';

-- Running upgrade 6e2d4a9b7c1f -> 3f8b6c2a9d17

CREATE TABLE organizations (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(200) NOT NULL, 
    logo_original_filename VARCHAR(255), 
    logo_stored_filename VARCHAR(255), 
    banner_original_filename VARCHAR(255), 
    banner_stored_filename VARCHAR(255), 
    updated_at DATETIME, 
    PRIMARY KEY (id)
);

CREATE TABLE blocklist_entries (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    entry_type VARCHAR(10) NOT NULL, 
    value VARCHAR(255) NOT NULL, 
    reason VARCHAR(255), 
    created_at DATETIME, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_blocklist_type_value UNIQUE (entry_type, value)
);

UPDATE alembic_version SET version_num='3f8b6c2a9d17' WHERE alembic_version.version_num = '6e2d4a9b7c1f';

-- Running upgrade 3f8b6c2a9d17 -> 829288d02ee8

ALTER TABLE candidates ADD COLUMN application_token VARCHAR(64);

ALTER TABLE candidates ADD COLUMN application_token_expires_at DATETIME;

CREATE UNIQUE INDEX ix_candidates_application_token ON candidates (application_token);

ALTER TABLE interviews ADD COLUMN confirmation_code VARCHAR(9);

ALTER TABLE interviews ADD COLUMN meeting_link VARCHAR(500);

ALTER TABLE interviews ADD COLUMN google_event_id VARCHAR(255);

CREATE UNIQUE INDEX ix_interviews_confirmation_code ON interviews (confirmation_code);

ALTER TABLE meeting_stage_templates ADD COLUMN interviewer_user_id INTEGER;

ALTER TABLE meeting_stage_templates ADD CONSTRAINT fk_meeting_stage_templates_interviewer_user_id FOREIGN KEY(interviewer_user_id) REFERENCES users (id);

UPDATE alembic_version SET version_num='829288d02ee8' WHERE alembic_version.version_num = '3f8b6c2a9d17';

-- Running upgrade 829288d02ee8 -> 0119ddf4a46f

ALTER TABLE candidates ADD COLUMN address_line1 VARCHAR(255);

ALTER TABLE candidates ADD COLUMN postal_code VARCHAR(20);

ALTER TABLE candidates ADD COLUMN work_authorized BOOL;

ALTER TABLE candidates ADD COLUMN requires_visa_sponsorship BOOL;

UPDATE alembic_version SET version_num='0119ddf4a46f' WHERE alembic_version.version_num = '829288d02ee8';

-- Running upgrade 0119ddf4a46f -> f227f9367231

ALTER TABLE candidates ADD COLUMN disqualified_at DATETIME;

ALTER TABLE candidates ADD COLUMN rejection_email_sent_at DATETIME;

UPDATE alembic_version SET version_num='f227f9367231' WHERE alembic_version.version_num = '0119ddf4a46f';

-- Running upgrade f227f9367231 -> af0a382c94da

ALTER TABLE organizations ADD COLUMN scheduling_timezone VARCHAR(64) NOT NULL DEFAULT 'UTC';

ALTER TABLE organizations ADD COLUMN scheduling_working_hours_start INTEGER NOT NULL DEFAULT '9';

ALTER TABLE organizations ADD COLUMN scheduling_working_hours_end INTEGER NOT NULL DEFAULT '17';

ALTER TABLE organizations ADD COLUMN scheduling_days JSON NOT NULL DEFAULT '[0, 1, 2, 3, 4]';

UPDATE alembic_version SET version_num='af0a382c94da' WHERE alembic_version.version_num = 'f227f9367231';


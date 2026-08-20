from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def iso_utc(dt):
    """Serializes a naive UTC datetime (as produced by datetime.utcnow(), which
    is how every timestamp in this app is stored) with an explicit 'Z' suffix.
    Without it, JS's `new Date(iso)` treats an offset-less date-time string as
    *local* time rather than UTC, silently shifting it by the browser's
    timezone offset — same clock digits, wrong instant."""
    return dt.isoformat() + 'Z' if dt else None


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='recruiter')  # admin, recruiter, interviewer
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self):
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": iso_utc(self.created_at)
        }


class CalendarConnection(db.Model):
    """A recruiter/interviewer's connected Google Calendar. Belongs to a User
    (not a Job or MeetingStageTemplate) — one connection is reusable across
    every stage that User is assigned to interview for, so it only needs to
    be connected once. unique=True on user_id means reconnecting overwrites
    the existing row (upsert) instead of creating a second connection."""
    __tablename__ = 'calendar_connections'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    google_email = db.Column(db.String(120), nullable=False)
    # Encrypted at rest with Fernet (see google_calendar.encrypt_token) — this
    # is a long-lived credential (until revoked), unlike access_token below,
    # which is short-lived (~1 hour) and low-value if it ever leaked, so it's
    # kept in plaintext the same way a session token would be.
    encrypted_refresh_token = db.Column(db.Text, nullable=False)
    access_token = db.Column(db.Text, nullable=True)
    token_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # backref='calendar_connection' mirrors CandidateAccount.candidates below
    # (backref='candidate_account') — the FK lives here, User just gets the
    # reverse accessor. uselist=False since it's one connection per user.
    user = db.relationship('User', backref=db.backref('calendar_connection', uselist=False))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "google_email": self.google_email,
            "created_at": iso_utc(self.created_at),
        }


class CandidateAccount(db.Model):
    """A prospective candidate's own login — distinct from Candidate, which is
    the per-job application/pipeline record recruiters manage. One person can
    hold a single CandidateAccount and (eventually) apply to many jobs; linking
    an account to specific Candidate rows is future work, not modeled yet."""
    __tablename__ = 'candidate_accounts'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # backref='candidate_account' mirrors Job.candidates below (backref='job') —
    # the FK lives on Candidate, this side just gets the reverse accessor.
    candidates = db.relationship('Candidate', backref='candidate_account', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def to_dict(self):
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "is_active": self.is_active,
            "created_at": iso_utc(self.created_at),
        }


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(50), default='Draft')  # Published, Draft, Closed
    job_type = db.Column(db.JSON, default=list)  # subset of VALID_JOB_TYPES
    city = db.Column(db.String(120))
    state = db.Column(db.String(60))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(60), default='USA')
    min_salary = db.Column(db.Float)
    max_salary = db.Column(db.Float)
    salary_period = db.Column(db.String(20))  # Hourly, Salary
    highlights = db.Column(db.JSON, default=list)  # free-form tags, e.g. "401(k)"
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_STATUSES = ('Published', 'Draft', 'Closed')
    VALID_JOB_TYPES = ('Full-time', 'Part-time', 'Remote')
    VALID_SALARY_PERIODS = ('Hourly', 'Salary')

    candidates = db.relationship('Candidate', backref='job', lazy=True)
    meeting_stage_templates = db.relationship(
        'MeetingStageTemplate', backref='job', cascade='all, delete-orphan', lazy=True
    )

    @property
    def screening_questions(self):
        """Every pre-screening question across all of this job's stages —
        questions live on a stage (see MeetingStageTemplate.screening_questions)
        but a candidate applying to the job answers all of them, regardless of
        which stage each one belongs to."""
        return [
            q
            for t in sorted(self.meeting_stage_templates, key=lambda t: (t.sort_order, t.id))
            for q in sorted(t.screening_questions, key=lambda q: (q.sort_order, q.id))
        ]

    @property
    def onboarding_items(self):
        """Every onboarding document item across all of this job's stages —
        same aggregation as screening_questions above, for the same reason: a
        candidate applying to the job is on the hook for all of them,
        regardless of which stage each one belongs to."""
        return [
            item
            for t in sorted(self.meeting_stage_templates, key=lambda t: (t.sort_order, t.id))
            for item in sorted(t.onboarding_items, key=lambda i: (i.sort_order, i.id))
        ]

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "job_type": self.job_type or [],
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "location": ", ".join(filter(None, [self.city, self.state])) or None,
            "min_salary": self.min_salary,
            "max_salary": self.max_salary,
            "salary_period": self.salary_period,
            "highlights": self.highlights or [],
            "description": self.description,
            "created_at": iso_utc(self.created_at),
            "candidate_count": len(self.candidates),
            "meeting_stages": [
                t.to_dict()
                for t in sorted(self.meeting_stage_templates, key=lambda t: (t.sort_order, t.id))
            ]
        }


class MeetingStageTemplate(db.Model):
    __tablename__ = 'meeting_stage_templates'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    meeting_type = db.Column(db.String(50), nullable=False)
    stage_name = db.Column(db.String(100), nullable=False)  # e.g. CHHA, Orientation
    duration_minutes = db.Column(db.Integer)  # only meaningful for interview-type stages
    # Only meaningful for 'In-person orientation' - how many candidates a
    # single session of this stage is meant to hold. This is a *default* the
    # frontend pre-fills the capacity field with when adding a session for
    # this stage - each session still stores its own Interview.capacity and
    # can be set differently after the fact; nothing here enforces a cap.
    default_capacity = db.Column(db.Integer)
    # Only meaningful for the two in-person types. Same "default, not
    # enforced" relationship to Interview.location as default_capacity has to
    # Interview.capacity above.
    location = db.Column(db.String(255))
    instructions = db.Column(db.Text)  # optional - directions, suite number, etc.
    # How far in advance a candidate can book a session for this stage.
    scheduling_window_days = db.Column(db.Integer, default=7, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_MEETING_TYPES = (
        'Virtual interview',
        'In-person interview',
        'In-person orientation',
        'Instant meeting link',
    )

    screening_questions = db.relationship(
        'ScreeningQuestion', backref='meeting_stage_template', cascade='all, delete-orphan', lazy=True
    )
    onboarding_items = db.relationship(
        'OnboardingDocumentItem', backref='meeting_stage_template', cascade='all, delete-orphan', lazy=True
    )

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "meeting_type": self.meeting_type,
            "stage_name": self.stage_name,
            "duration_minutes": self.duration_minutes,
            "default_capacity": self.default_capacity,
            "location": self.location,
            "instructions": self.instructions,
            "scheduling_window_days": self.scheduling_window_days,
            "sort_order": self.sort_order,
        }


class ScreeningQuestion(db.Model):
    """A pre-screening question defined on a meeting stage (the Stage editor's
    "Pre-screen" tab). Candidates progressing through the job get one
    CandidateScreeningAnswer per question, across all of the job's stages —
    see Job.screening_questions."""
    __tablename__ = 'screening_questions'

    id = db.Column(db.Integer, primary_key=True)
    meeting_stage_template_id = db.Column(
        db.Integer, db.ForeignKey('meeting_stage_templates.id'), nullable=False
    )
    question_text = db.Column(db.String(500), nullable=False)
    question_label = db.Column(db.String(200))  # short internal name, e.g. "Car insurance"
    # A multiple-choice question candidates pick one option from. Both empty
    # (list, not None) means a free-text question with no fixed options.
    answer_options = db.Column(db.JSON, default=list, nullable=False)
    # Subset of answer_options that qualifies a candidate to proceed — anything
    # picked that isn't in here is a disqualifying answer.
    qualified_answers = db.Column(db.JSON, default=list, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "meeting_stage_template_id": self.meeting_stage_template_id,
            "question_text": self.question_text,
            "question_label": self.question_label,
            "answer_options": self.answer_options or [],
            "qualified_answers": self.qualified_answers or [],
            "sort_order": self.sort_order,
        }


class OnboardingDocumentItem(db.Model):
    """A required (or optional) onboarding document defined on a meeting stage
    (the Stage editor's "Onboarding" tab). Candidates progressing through the
    job submit one CandidateDocument per item, across all of the job's stages
    — see Job.onboarding_items. Mirrors ScreeningQuestion's shape/scoping."""
    __tablename__ = 'onboarding_document_items'

    id = db.Column(db.Integer, primary_key=True)
    meeting_stage_template_id = db.Column(
        db.Integer, db.ForeignKey('meeting_stage_templates.id'), nullable=False
    )
    description = db.Column(db.String(500), nullable=False)
    # Named item_type, not type, to avoid shadowing the builtin - same reason
    # Interview.meeting_type isn't just called type. Only 'file_upload' exists
    # today; kept as a field for other item types later (e.g. an e-sign doc).
    item_type = db.Column(db.String(30), default='file_upload', nullable=False)
    required = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_TYPES = ('file_upload',)

    def to_dict(self):
        return {
            "id": self.id,
            "meeting_stage_template_id": self.meeting_stage_template_id,
            "description": self.description,
            "type": self.item_type,
            "required": self.required,
            "sort_order": self.sort_order,
        }


interview_candidates = db.Table(
    'interview_candidates',
    db.Column('interview_id', db.Integer, db.ForeignKey('interviews.id'), primary_key=True),
    db.Column('candidate_id', db.Integer, db.ForeignKey('candidates.id'), primary_key=True),
)


class Interview(db.Model):
    __tablename__ = 'interviews'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True)
    # Nullable: an interview not tied to a job (job_id is None) can't be tied to
    # one of that job's stages either. stage_name stays the source of truth for
    # display and for ad-hoc interviews with no template; this FK is the real
    # link back to the template when there is one, instead of matching by name.
    meeting_stage_template_id = db.Column(
        db.Integer, db.ForeignKey('meeting_stage_templates.id'), nullable=True
    )
    stage_name = db.Column(db.String(100), nullable=False)  # e.g. Orientation, Technical Interview, Onsite
    meeting_type = db.Column(db.String(50), nullable=False)  # Interview, Orientation, or Other
    location = db.Column(db.String(255))  # room, address, or meeting link
    scheduled_start = db.Column(db.DateTime, nullable=False)
    scheduled_end = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_MEETING_TYPES = ('Interview', 'Orientation', 'Other')

    job = db.relationship('Job', backref='interviews')
    meeting_stage_template = db.relationship('MeetingStageTemplate')
    candidates = db.relationship('Candidate', secondary=interview_candidates, backref='interviews')

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_title": self.job.title if self.job else None,
            "meeting_stage_template_id": self.meeting_stage_template_id,
            "stage_name": self.stage_name,
            "meeting_type": self.meeting_type,
            "location": self.location,
            "scheduled_start": iso_utc(self.scheduled_start),
            "scheduled_end": iso_utc(self.scheduled_end),
            "capacity": self.capacity,
            "scheduled_count": len(self.candidates),
            "candidates": [{"id": c.id, "name": c.display_name} for c in self.candidates],
            "created_at": iso_utc(self.created_at)
        }


class Candidate(db.Model):
    __tablename__ = 'candidates'

    id = db.Column(db.Integer, primary_key=True)
    # For an account-linked candidate (candidate_account_id set), these three
    # are a point-in-time snapshot taken at registration — NOT the source of
    # truth. display_name/display_email/display_phone below are: they read
    # live from candidate_account when linked, and everything that surfaces a
    # candidate's contact info (to_dict, to_detail_dict, Interview.to_dict's
    # enrolled-candidate list) goes through those, not these columns directly.
    # The columns stay NOT NULL and still get written on creation because
    # hand-added candidates (candidate_account_id is None) have nowhere else
    # to store their info — they're the only source of truth for those rows,
    # and dropping them would break that case entirely, not just the linked
    # one. They also act as a fallback if candidate_account is ever missing
    # (e.g. a deleted account) instead of surfacing an empty/null contact.
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True)
    # Set when this row was created from a candidate's self-registration
    # (routes/candidate_auth.py) rather than by a recruiter. Nullable because
    # recruiters can still add candidates by hand with no account behind them.
    candidate_account_id = db.Column(
        db.Integer, db.ForeignKey('candidate_accounts.id'), nullable=True
    )
    stage = db.Column(db.String(50), default='Applied')  # e.g. Applied, Interview, Offer, Hired, Rejected
    status = db.Column(db.String(50), default='Active')
    interviewer = db.Column(db.String(120))
    scheduled = db.Column(db.Boolean, default=False)
    city = db.Column(db.String(120))
    state = db.Column(db.String(60))
    source = db.Column(db.String(120))  # e.g. Indeed, Referral
    resume_original_filename = db.Column(db.String(255))
    resume_stored_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    VALID_STAGES = ('Applied', 'Interview', 'Offer', 'Hired', 'Rejected')

    screening_answers = db.relationship(
        'CandidateScreeningAnswer', backref='candidate', cascade='all, delete-orphan', lazy=True
    )
    stage_progress = db.relationship(
        'CandidateStageProgress', backref='candidate', cascade='all, delete-orphan', lazy=True
    )
    documents = db.relationship(
        'CandidateDocument', backref='candidate', cascade='all, delete-orphan', lazy=True
    )

    @property
    def location(self):
        return ", ".join(filter(None, [self.city, self.state])) or None

    @property
    def display_name(self):
        return self.candidate_account.name if self.candidate_account else self.name

    @property
    def display_email(self):
        return self.candidate_account.email if self.candidate_account else self.email

    @property
    def display_phone(self):
        return self.candidate_account.phone if self.candidate_account else self.phone

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.display_name,
            "email": self.display_email,
            "phone": self.display_phone,
            "job_id": self.job_id,
            "job_title": self.job.title if self.job else None,
            "candidate_account_id": self.candidate_account_id,
            "stage": self.stage,
            "status": self.status,
            "interviewer": self.interviewer,
            "scheduled": self.scheduled,
            "city": self.city,
            "state": self.state,
            "location": self.location,
            "source": self.source,
            "has_resume": self.resume_stored_filename is not None,
            "resume_filename": self.resume_original_filename,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at or self.created_at),
            "current_stage": self._current_stage_summary(),
        }

    def _current_stage_summary(self):
        """The stage progress row to surface on the candidates list: the
        soonest upcoming one, else the most recently touched one."""
        if not self.stage_progress:
            return None
        upcoming = [p for p in self.stage_progress if p.status == 'Upcoming' and p.scheduled_at]
        if upcoming:
            progress = min(upcoming, key=lambda p: p.scheduled_at)
        else:
            progress = max(self.stage_progress, key=lambda p: p.updated_at or p.id)
        return {
            "meeting_stage_template_id": progress.meeting_stage_template_id,
            "stage_name": progress.meeting_stage_template.stage_name
            if progress.meeting_stage_template
            else None,
            "status": progress.status,
            "scheduled_at": iso_utc(progress.scheduled_at),
        }

    def to_detail_dict(self):
        data = self.to_dict()
        # Job.screening_questions is already ordered (by stage, then question
        # sort_order) — re-sorting by question sort_order alone would scramble
        # that, since sort_order only orders questions within their own stage.
        questions = self.job.screening_questions if self.job else []
        answers_by_question = {a.question_id: a.answer_text for a in self.screening_answers}
        progress_by_template = {p.meeting_stage_template_id: p for p in self.stage_progress}
        templates = (
            sorted(self.job.meeting_stage_templates, key=lambda t: (t.sort_order, t.id))
            if self.job
            else []
        )

        data.update(
            {
                "screening_answers": [
                    {
                        "question_id": q.id,
                        "question_text": q.question_text,
                        "answer_options": q.answer_options or [],
                        "answer_text": answers_by_question.get(q.id),
                    }
                    for q in questions
                ],
                "stages": [
                    {
                        "meeting_stage_template_id": t.id,
                        "stage_name": t.stage_name,
                        "meeting_type": t.meeting_type,
                        **(
                            progress_by_template[t.id].to_dict()
                            if t.id in progress_by_template
                            else {
                                "id": None,
                                "status": 'Upcoming',
                                "scheduled_at": None,
                                "location": None,
                                "notes": None,
                                "score_communication": None,
                                "score_energy": None,
                                "score_relevant_experience": None,
                                "cancellation_reason": None,
                                "prompt_reschedule": None,
                            }
                        ),
                    }
                    for t in templates
                ],
                "documents": {d.onboarding_item_id: d.to_dict() for d in self.documents},
            }
        )
        return data


class CandidateScreeningAnswer(db.Model):
    __tablename__ = 'candidate_screening_answers'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('screening_questions.id'), nullable=False)
    answer_text = db.Column(db.Text)

    __table_args__ = (db.UniqueConstraint('candidate_id', 'question_id', name='uq_candidate_question'),)

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "question_id": self.question_id,
            "answer_text": self.answer_text,
        }


class CandidateStageProgress(db.Model):
    """A candidate's progress through one of their job's meeting stages:
    scheduling, status, interviewer notes, and scorecard ratings."""
    __tablename__ = 'candidate_stage_progress'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    meeting_stage_template_id = db.Column(
        db.Integer, db.ForeignKey('meeting_stage_templates.id'), nullable=False
    )
    status = db.Column(db.String(30), default='Upcoming', nullable=False)
    scheduled_at = db.Column(db.DateTime)
    location = db.Column(db.String(255))
    notes = db.Column(db.Text)
    score_communication = db.Column(db.Integer)
    score_energy = db.Column(db.Integer)
    score_relevant_experience = db.Column(db.Integer)
    # Set together when a recruiter cancels via the "Cancel interview" modal.
    # Neither triggers any actual notification today - there's no email/SMS
    # infrastructure in this app yet, and no candidate-facing reschedule flow
    # for prompt_reschedule to hand off to - they're just recorded so the
    # recruiter's stated intent isn't lost.
    cancellation_reason = db.Column(db.Text)
    prompt_reschedule = db.Column(db.Boolean)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    VALID_STATUSES = ('Upcoming', 'Completed', 'Cancelled', 'No show')

    __table_args__ = (
        db.UniqueConstraint('candidate_id', 'meeting_stage_template_id', name='uq_candidate_stage'),
    )

    meeting_stage_template = db.relationship('MeetingStageTemplate')

    def to_dict(self):
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "meeting_stage_template_id": self.meeting_stage_template_id,
            "status": self.status,
            "scheduled_at": iso_utc(self.scheduled_at),
            "location": self.location,
            "notes": self.notes,
            "score_communication": self.score_communication,
            "score_energy": self.score_energy,
            "score_relevant_experience": self.score_relevant_experience,
            "cancellation_reason": self.cancellation_reason,
            "prompt_reschedule": self.prompt_reschedule,
        }


class CandidateDocument(db.Model):
    __tablename__ = 'candidate_documents'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    onboarding_item_id = db.Column(
        db.Integer, db.ForeignKey('onboarding_document_items.id'), nullable=False
    )
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('candidate_id', 'onboarding_item_id', name='uq_candidate_onboarding_item'),
    )

    onboarding_item = db.relationship('OnboardingDocumentItem')

    def to_dict(self):
        return {
            "id": self.id,
            "onboarding_item_id": self.onboarding_item_id,
            "original_filename": self.original_filename,
            "uploaded_at": iso_utc(self.uploaded_at),
        }

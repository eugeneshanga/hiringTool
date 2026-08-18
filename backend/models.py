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
    screening_questions = db.relationship(
        'JobScreeningQuestion', backref='job', cascade='all, delete-orphan', lazy=True
    )

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
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_MEETING_TYPES = (
        'Virtual interview',
        'In-person interview',
        'In-person orientation',
        'Instant meeting link',
    )

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "meeting_type": self.meeting_type,
            "stage_name": self.stage_name,
            "duration_minutes": self.duration_minutes,
            "sort_order": self.sort_order,
        }


class JobScreeningQuestion(db.Model):
    """A reusable pre-screening question defined on a job. Candidates applying
    to that job get one CandidateScreeningAnswer per question."""
    __tablename__ = 'job_screening_questions'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    question_text = db.Column(db.String(500), nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "question_text": self.question_text,
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
    stage_name = db.Column(db.String(100), nullable=False)  # e.g. Orientation, Technical Interview, Onsite
    meeting_type = db.Column(db.String(50), nullable=False)  # Interview, Orientation, or Other
    location = db.Column(db.String(255))  # room, address, or meeting link
    scheduled_start = db.Column(db.DateTime, nullable=False)
    scheduled_end = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_MEETING_TYPES = ('Interview', 'Orientation', 'Other')

    job = db.relationship('Job', backref='interviews')
    candidates = db.relationship('Candidate', secondary=interview_candidates, backref='interviews')

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_title": self.job.title if self.job else None,
            "stage_name": self.stage_name,
            "meeting_type": self.meeting_type,
            "location": self.location,
            "scheduled_start": iso_utc(self.scheduled_start),
            "scheduled_end": iso_utc(self.scheduled_end),
            "capacity": self.capacity,
            "scheduled_count": len(self.candidates),
            "candidates": [{"id": c.id, "name": c.name} for c in self.candidates],
            "created_at": iso_utc(self.created_at)
        }


class Candidate(db.Model):
    __tablename__ = 'candidates'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True)
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

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "job_id": self.job_id,
            "job_title": self.job.title if self.job else None,
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
        questions = (
            sorted(self.job.screening_questions, key=lambda q: (q.sort_order, q.id)) if self.job else []
        )
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
                            }
                        ),
                    }
                    for t in templates
                ],
                "documents": {d.doc_type: d.to_dict() for d in self.documents},
            }
        )
        return data


class CandidateScreeningAnswer(db.Model):
    __tablename__ = 'candidate_screening_answers'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('job_screening_questions.id'), nullable=False)
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
        }


# (doc_type, label) — the fixed onboarding document checklist shown on every candidate.
CANDIDATE_DOCUMENT_TYPES = (
    ("drivers_license", "Please Upload a Government Issued Driver's License"),
    ("nursing_license", "Please Upload your Nursing License"),
    ("ssn_card", "Please Upload Your Social Security Card"),
    ("xray_ppd", "Please send your current X-ray or PPD Results"),
)


class CandidateDocument(db.Model):
    __tablename__ = 'candidate_documents'

    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidates.id'), nullable=False)
    doc_type = db.Column(db.String(30), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('candidate_id', 'doc_type', name='uq_candidate_doctype'),)

    def to_dict(self):
        return {
            "id": self.id,
            "doc_type": self.doc_type,
            "original_filename": self.original_filename,
            "uploaded_at": iso_utc(self.uploaded_at),
        }

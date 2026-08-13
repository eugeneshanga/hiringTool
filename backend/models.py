from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='recruiter')  # admin, recruiter, interviewer
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat()
        }


class Job(db.Model):
    __tablename__ = 'jobs'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    department = db.Column(db.String(100))
    location = db.Column(db.String(120))
    status = db.Column(db.String(50), default='Open')  # Open, Closed, Draft
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    candidates = db.relationship('Candidate', backref='job', lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "department": self.department,
            "location": self.location,
            "status": self.status,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "candidate_count": len(self.candidates)
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
    meeting_type = db.Column(db.String(100), nullable=False)  # e.g. In-person orientation, Video call
    location = db.Column(db.String(255))  # room, address, or meeting link
    scheduled_start = db.Column(db.DateTime, nullable=False)
    scheduled_end = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, default=1, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
            "scheduled_start": self.scheduled_start.isoformat(),
            "scheduled_end": self.scheduled_end.isoformat(),
            "capacity": self.capacity,
            "scheduled_count": len(self.candidates),
            "candidates": [{"id": c.id, "name": c.name} for c in self.candidates],
            "created_at": self.created_at.isoformat()
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    VALID_STAGES = ('Applied', 'Interview', 'Offer', 'Hired', 'Rejected')

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "job_id": self.job_id,
            "stage": self.stage,
            "status": self.status,
            "interviewer": self.interviewer,
            "scheduled": self.scheduled,
            "created_at": self.created_at.isoformat()
        }

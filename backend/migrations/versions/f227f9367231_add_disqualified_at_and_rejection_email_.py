"""add disqualified_at and rejection_email_sent_at to candidates

Revision ID: f227f9367231
Revises: 0119ddf4a46f
Create Date: 2026-08-25 13:40:00.000000

Note: autogenerate also picked up the same pre-existing model/DB drift noted
in prior migrations (jobs.location/department, job_type/highlights column
types, NOT NULL on users.first_name/last_name and
meeting_stage_templates.sort_order, interviews.meeting_type length) - left
out again, unrelated to this change.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f227f9367231'
down_revision = '0119ddf4a46f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('disqualified_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('rejection_email_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_column('rejection_email_sent_at')
        batch_op.drop_column('disqualified_at')

"""add public apply flow fields

Revision ID: 829288d02ee8
Revises: 3f8b6c2a9d17
Create Date: 2026-08-24 13:18:04.919698

Note: autogenerate also picked up pre-existing drift between models.py and
this dev DB that predates this change (jobs.location/department,
job_type/highlights column types, NOT NULL on users.first_name/last_name and
meeting_stage_templates.sort_order, interviews.meeting_type length) -
deliberately left out of this migration since it's unrelated; worth its own
follow-up migration.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '829288d02ee8'
down_revision = '3f8b6c2a9d17'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('application_token', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('application_token_expires_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_candidates_application_token'), ['application_token'], unique=True)

    with op.batch_alter_table('interviews', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confirmation_code', sa.String(length=9), nullable=True))
        batch_op.add_column(sa.Column('meeting_link', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('google_event_id', sa.String(length=255), nullable=True))
        batch_op.create_index(batch_op.f('ix_interviews_confirmation_code'), ['confirmation_code'], unique=True)

    with op.batch_alter_table('meeting_stage_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('interviewer_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_meeting_stage_templates_interviewer_user_id',
            'users', ['interviewer_user_id'], ['id'],
        )


def downgrade():
    with op.batch_alter_table('meeting_stage_templates', schema=None) as batch_op:
        batch_op.drop_constraint('fk_meeting_stage_templates_interviewer_user_id', type_='foreignkey')
        batch_op.drop_column('interviewer_user_id')

    with op.batch_alter_table('interviews', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_interviews_confirmation_code'))
        batch_op.drop_column('google_event_id')
        batch_op.drop_column('meeting_link')
        batch_op.drop_column('confirmation_code')

    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_candidates_application_token'))
        batch_op.drop_column('application_token_expires_at')
        batch_op.drop_column('application_token')

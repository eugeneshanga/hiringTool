"""add address, work authorization, and visa sponsorship fields to candidates

Revision ID: 0119ddf4a46f
Revises: 829288d02ee8
Create Date: 2026-08-25 11:51:24.037713

Note: autogenerate also picked up the same pre-existing model/DB drift noted
in 829288d02ee8 (jobs.location/department, job_type/highlights column types,
NOT NULL on users.first_name/last_name and meeting_stage_templates.sort_order,
interviews.meeting_type length) - left out again for the same reason: it
predates this change and is unrelated to it.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0119ddf4a46f'
down_revision = '829288d02ee8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address_line1', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('postal_code', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('work_authorized', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('requires_visa_sponsorship', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_column('requires_visa_sponsorship')
        batch_op.drop_column('work_authorized')
        batch_op.drop_column('postal_code')
        batch_op.drop_column('address_line1')

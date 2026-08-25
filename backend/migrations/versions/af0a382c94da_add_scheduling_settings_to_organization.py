"""add scheduling settings to organization

Revision ID: af0a382c94da
Revises: f227f9367231
Create Date: 2026-08-25 15:23:15.019544

Note: autogenerate also picked up the same pre-existing model/DB drift noted
in prior migrations (jobs.location/department, job_type/highlights column
types, NOT NULL on users.first_name/last_name and
meeting_stage_templates.sort_order, interviews.meeting_type length) - left
out again, unrelated to this change.

server_default is set on each new column (not just the Python-side
db.Column default=...) since these are NOT NULL columns being added to a
table that may already have a row (this app's single Organization record) -
without it, SQLite has nothing to backfill that existing row with.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'af0a382c94da'
down_revision = 'f227f9367231'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'scheduling_timezone', sa.String(length=64), nullable=False, server_default='UTC',
        ))
        batch_op.add_column(sa.Column(
            'scheduling_working_hours_start', sa.Integer(), nullable=False, server_default='9',
        ))
        batch_op.add_column(sa.Column(
            'scheduling_working_hours_end', sa.Integer(), nullable=False, server_default='17',
        ))
        batch_op.add_column(sa.Column(
            'scheduling_days', sa.JSON(), nullable=False, server_default='[0, 1, 2, 3, 4]',
        ))


def downgrade():
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_column('scheduling_days')
        batch_op.drop_column('scheduling_working_hours_end')
        batch_op.drop_column('scheduling_working_hours_start')
        batch_op.drop_column('scheduling_timezone')

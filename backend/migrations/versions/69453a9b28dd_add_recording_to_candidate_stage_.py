"""add recording to candidate stage progress

Revision ID: 69453a9b28dd
Revises: 6ab7d9747c78
Create Date: 2026-09-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '69453a9b28dd'
down_revision = '6ab7d9747c78'
branch_labels = None
depends_on = None

# The uploaded interview recording for one candidate's one stage - same
# storage convention as Candidate.resume_stored_filename (file_storage.py).


def upgrade():
    with op.batch_alter_table('candidate_stage_progress', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recording_original_filename', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('recording_stored_filename', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('candidate_stage_progress', schema=None) as batch_op:
        batch_op.drop_column('recording_stored_filename')
        batch_op.drop_column('recording_original_filename')

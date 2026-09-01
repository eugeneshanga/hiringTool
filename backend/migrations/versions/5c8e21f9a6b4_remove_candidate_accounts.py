"""remove candidate accounts

Revision ID: 5c8e21f9a6b4
Revises: af0a382c94da
Create Date: 2026-09-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c8e21f9a6b4'
down_revision = 'af0a382c94da'
branch_labels = None
depends_on = None

# Candidates never got their own login in practice - see ApplicationStatusPage
# / routes/status.py for the phone/confirmation-code alternative that
# replaced it. Drops candidates.candidate_account_id (and its FK) before
# dropping candidate_accounts itself - the reverse order fails on any
# database that enforces foreign keys (see 213d189a3b5f's fix for the exact
# same class of bug).


def upgrade():
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_constraint('fk_candidates_candidate_account_id', type_='foreignkey')
        batch_op.drop_column('candidate_account_id')
    op.drop_table('candidate_accounts')


def downgrade():
    op.create_table(
        'candidate_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=120), nullable=False),
        sa.Column('last_name', sa.String(length=120), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('candidate_account_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_candidates_candidate_account_id', 'candidate_accounts', ['candidate_account_id'], ['id'],
        )

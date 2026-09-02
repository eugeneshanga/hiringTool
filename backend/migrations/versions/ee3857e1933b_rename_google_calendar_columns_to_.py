"""rename google calendar columns to microsoft

Revision ID: ee3857e1933b
Revises: 5c8e21f9a6b4
Create Date: 2026-09-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ee3857e1933b'
down_revision = '5c8e21f9a6b4'
branch_labels = None
depends_on = None

# Google Calendar -> Microsoft/Outlook Calendar full replacement (see
# microsoft_calendar.py, which replaces the deleted google_calendar.py).
# Plain column renames, same type/nullability on both sides, so batch mode
# (needed for SQLite, harmless on MariaDB) is all this needs - no data
# migration, since the values themselves (an email address, an event id)
# mean the same thing under the new provider.


def upgrade():
    with op.batch_alter_table('calendar_connections', schema=None) as batch_op:
        batch_op.alter_column('google_email', new_column_name='account_email', existing_type=sa.String(length=120))
    with op.batch_alter_table('interviews', schema=None) as batch_op:
        batch_op.alter_column(
            'google_event_id', new_column_name='calendar_event_id', existing_type=sa.String(length=255),
        )


def downgrade():
    with op.batch_alter_table('interviews', schema=None) as batch_op:
        batch_op.alter_column(
            'calendar_event_id', new_column_name='google_event_id', existing_type=sa.String(length=255),
        )
    with op.batch_alter_table('calendar_connections', schema=None) as batch_op:
        batch_op.alter_column('account_email', new_column_name='google_email', existing_type=sa.String(length=120))

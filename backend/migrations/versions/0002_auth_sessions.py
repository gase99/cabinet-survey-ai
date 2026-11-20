"""Revocable sessions. Existing stateless tokens require a new sign-in."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('auth_sessions', sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('refresh_digest',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('revoked',sa.Boolean(),nullable=False))
    op.create_index('ix_auth_sessions_user_id','auth_sessions',['user_id'])


def downgrade():
    op.drop_index('ix_auth_sessions_user_id',table_name='auth_sessions')
    op.drop_table('auth_sessions')

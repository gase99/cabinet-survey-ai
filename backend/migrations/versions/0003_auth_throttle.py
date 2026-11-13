"""Shared database-backed auth rate limiting."""
from alembic import op
import sqlalchemy as sa
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('auth_throttles',sa.Column('key',sa.String(64),primary_key=True),
        sa.Column('bucket',sa.Integer(),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False))
    op.create_index('ix_auth_throttles_bucket','auth_throttles',['bucket'])


def downgrade():
    op.drop_index('ix_auth_throttles_bucket',table_name='auth_throttles')
    op.drop_table('auth_throttles')

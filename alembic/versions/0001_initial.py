import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("payment_id", sa.Uuid(), primary_key=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("metadata", JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("webhook_status", sa.String(16), nullable=False),
        sa.Column("gateway_failures", sa.Integer(), nullable=False),
        sa.Column("webhook_failures", sa.Integer(), nullable=False),
        sa.Column("gateway_next_at", sa.DateTime(timezone=True)),
        sa.Column("webhook_next_at", sa.DateTime(timezone=True)),
        sa.Column("event_id", sa.Uuid()),
        sa.Column("webhook_body", sa.LargeBinary()),
        sa.Column("dlq_published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "outbox",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("payment_id", sa.Uuid(), sa.ForeignKey("payments.payment_id"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("outbox")
    op.drop_table("payments")

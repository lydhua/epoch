"""Create owner-scoped collections/items and immutable API attempt receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0001_practice"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.UniqueConstraint("owner_id", "id", name="uq_collections_owner_id"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_collection_name"),
    )
    op.create_table(
        "items",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("collection_id", sa.Uuid, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("current_schedule", sa.JSON, nullable=False),
        sa.UniqueConstraint("owner_id", "id", name="uq_items_owner_id"),
        sa.ForeignKeyConstraint(
            ["owner_id", "collection_id"],
            ["collections.owner_id", "collections.id"],
            name="fk_item_collection_owner",
        ),
        sa.CheckConstraint(
            "(archived AND next_due_at IS NULL) OR (NOT archived AND next_due_at IS NOT NULL)",
            name="ck_item_due_state",
        ),
    )
    op.create_index("ix_items_due", "items", ["owner_id", "archived", "next_due_at", "id"])
    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("item_id", sa.Uuid, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("event", sa.JSON, nullable=False),
        sa.Column("receipt", sa.JSON, nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "item_id"], ["items.owner_id", "items.id"], name="fk_attempt_item_owner"
        ),
        sa.UniqueConstraint("item_id", "occurred_at", name="uq_attempt_timestamp"),
    )
    op.create_index("ix_attempts_history", "attempts", ["owner_id", "item_id", "occurred_at"])


def downgrade():
    op.drop_table("attempts")
    op.drop_table("items")
    op.drop_table("collections")

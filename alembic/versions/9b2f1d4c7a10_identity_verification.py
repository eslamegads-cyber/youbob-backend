"""Add identity verification requests

Revision ID: 9b2f1d4c7a10
Revises: 6259b2e4cf6e
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b2f1d4c7a10"
down_revision: Union[str, Sequence[str], None] = "6259b2e4cf6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "identity_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "identity_verification_status",
            sa.String(),
            nullable=False,
            server_default="none",
        ),
    )

    op.create_table(
        "identity_verification_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column("national_id", sa.String(length=100), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id_front_path", sa.String(length=500), nullable=False),
        sa.Column("id_back_path", sa.String(length=500), nullable=False),
        sa.Column("face_front_path", sa.String(length=500), nullable=False),
        sa.Column("face_left_path", sa.String(length=500), nullable=False),
        sa.Column("face_right_path", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("reviewer_id", sa.Integer(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_identity_verification_requests_id",
        "identity_verification_requests",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_identity_verification_requests_user_id",
        "identity_verification_requests",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_identity_verification_requests_status",
        "identity_verification_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_identity_verification_requests_one_pending",
        "identity_verification_requests",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_identity_verification_requests_one_pending",
        table_name="identity_verification_requests",
    )
    op.drop_index(
        "ix_identity_verification_requests_status",
        table_name="identity_verification_requests",
    )
    op.drop_index(
        "ix_identity_verification_requests_user_id",
        table_name="identity_verification_requests",
    )
    op.drop_index(
        "ix_identity_verification_requests_id",
        table_name="identity_verification_requests",
    )
    op.drop_table("identity_verification_requests")
    op.drop_column("users", "identity_verification_status")
    op.drop_column("users", "identity_verified")

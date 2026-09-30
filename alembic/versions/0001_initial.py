"""Начальная схема БД

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("clerk", "manager", "executor", "admin")
DOC_STATUSES = ("зарегистрирован", "на рассмотрении", "на исполнении", "исполнен", "снят с контроля", "в архиве")
RES_STATUSES = ("на исполнении", "исполнена")
ATT_TYPES = ("source_scan", "execution_report", "other")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table("departments", _id(), sa.Column("name", sa.String(255), nullable=False), *_ts(),
                    sa.UniqueConstraint("name"))
    op.create_table("positions", _id(), sa.Column("name", sa.String(255), nullable=False),
                    sa.UniqueConstraint("name"))
    op.create_table("document_types", _id(), sa.Column("name", sa.String(255), nullable=False),
                    sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
                    sa.UniqueConstraint("name"))

    op.create_table(
        "users", _id(),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("login", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position_id", sa.Uuid(), sa.ForeignKey("positions.id", ondelete="RESTRICT")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_ts(),
        sa.UniqueConstraint("login"), sa.UniqueConstraint("email"),
        sa.CheckConstraint(_in("role", ROLES), name="role_valid"),
    )
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_department_id", "users", ["department_id"])

    op.create_table(
        "correspondents", _id(),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("inn", sa.String(12)),
        sa.Column("address", sa.Text()),
        sa.Column("phone", sa.String(64)),
        sa.Column("email", sa.String(255)),
        sa.Column("signer_full_name", sa.String(255)),
        *_ts(),
    )
    op.create_index("ix_correspondents_name", "correspondents", ["name"])
    op.create_index("ix_correspondents_inn", "correspondents", ["inn"])

    op.create_table(
        "registration_counters",
        sa.Column("year", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "incoming_documents", _id(),
        sa.Column("registration_number", sa.String(64), nullable=False),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column("registration_date", sa.Date(), nullable=False),
        sa.Column("correspondent_id", sa.Uuid(), sa.ForeignKey("correspondents.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("addressee", sa.String(255)),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("document_type_id", sa.Uuid(), sa.ForeignKey("document_types.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("execution_deadline", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.UniqueConstraint("registration_number"),
        sa.CheckConstraint("page_count >= 1", name="page_count_positive"),
        sa.CheckConstraint("execution_deadline >= registration_date", name="deadline_not_before_registration"),
        sa.CheckConstraint(_in("status", DOC_STATUSES), name="status_valid"),
        sa.CheckConstraint("(status = 'в архиве') = (archived_at IS NOT NULL)", name="archived_consistent"),
    )
    for column in ("received_date", "registration_date", "correspondent_id", "document_type_id",
                   "execution_deadline", "status", "created_by"):
        op.create_index(f"ix_incoming_documents_{column}", "incoming_documents", [column])
    op.execute("CREATE INDEX ix_incoming_documents_summary_trgm ON incoming_documents "
               "USING gin (summary gin_trgm_ops)")

    op.create_table(
        "resolutions", _id(),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("incoming_documents.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_executor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint(_in("status", RES_STATUSES), name="status_valid"),
    )
    for column in ("document_id", "assigned_executor_id", "status"):
        op.create_index(f"ix_resolutions_{column}", "resolutions", [column])

    op.create_table(
        "attachments", _id(),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("incoming_documents.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("attachment_type", sa.String(32), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("storage_key"),
        sa.CheckConstraint("size_bytes > 0", name="size_positive"),
        sa.CheckConstraint(_in("attachment_type", ATT_TYPES), name="type_valid"),
    )
    op.create_index("ix_attachments_document_id", "attachments", ["document_id"])

    op.create_table(
        "document_history", _id(),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("incoming_documents.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("old_status", sa.String(32)),
        sa.Column("new_status", sa.String(32)),
        sa.Column("comment", sa.Text()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.UniqueConstraint("seq"),
        sa.CheckConstraint(f"old_status IS NULL OR {_in('old_status', DOC_STATUSES)}", name="old_status_valid"),
        sa.CheckConstraint(f"new_status IS NULL OR {_in('new_status', DOC_STATUSES)}", name="new_status_valid"),
    )
    op.create_index("ix_document_history_document_id", "document_history", ["document_id"])


def downgrade() -> None:
    for table in ("document_history", "attachments", "resolutions", "incoming_documents",
                  "registration_counters", "correspondents", "users", "document_types", "positions",
                  "departments"):
        op.drop_table(table)

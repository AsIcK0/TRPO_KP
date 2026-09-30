"""ORM-модели SQLAlchemy 2.x. Pydantic-схемы живут отдельно, в app/schemas."""

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AttachmentType, DocumentStatus, ResolutionStatus, Role


def utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(enum_cls: type[StrEnum], length: int = 32) -> SAEnum:
    """VARCHAR + значения enum (без нативного PG ENUM, чтобы миграции оставались простыми)."""
    return SAEnum(enum_cls, native_enum=False, length=length, values_callable=lambda e: [m.value for m in e])


def _in(column: str, enum_cls: type[StrEnum]) -> str:
    return f"{column} IN ({', '.join(repr(m.value) for m in enum_cls)})"


class UUIDPk:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 server_default=func.now())


class Department(UUIDPk, Timestamps, Base):
    __tablename__ = "departments"
    name: Mapped[str] = mapped_column(String(255), unique=True)


class Position(UUIDPk, Base):
    __tablename__ = "positions"
    name: Mapped[str] = mapped_column(String(255), unique=True)


class DocumentType(UUIDPk, Base):
    __tablename__ = "document_types"
    name: Mapped[str] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", Role), name="role_valid"),)

    full_name: Mapped[str] = mapped_column(String(255))
    login: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, 16), index=True)
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    position_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("positions.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    department: Mapped[Department] = relationship(lazy="selectin")
    position: Mapped[Position | None] = relationship(lazy="selectin")


class Correspondent(UUIDPk, Timestamps, Base):
    __tablename__ = "correspondents"

    name: Mapped[str] = mapped_column(String(500), index=True)
    inn: Mapped[str | None] = mapped_column(String(12), index=True)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255))
    signer_full_name: Mapped[str | None] = mapped_column(String(255))


class RegistrationCounter(Base):
    """Счетчики регистрационных номеров (по году или сквозной, ключ 0). Инкремент атомарный."""

    __tablename__ = "registration_counters"
    year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_value: Mapped[int] = mapped_column(Integer, default=0)


class IncomingDocument(UUIDPk, Timestamps, Base):
    __tablename__ = "incoming_documents"
    __table_args__ = (
        CheckConstraint("page_count >= 1", name="page_count_positive"),
        CheckConstraint("execution_deadline >= registration_date", name="deadline_not_before_registration"),
        CheckConstraint(_in("status", DocumentStatus), name="status_valid"),
        CheckConstraint(f"(status = '{DocumentStatus.ARCHIVED.value}') = (archived_at IS NOT NULL)",
                        name="archived_consistent"),
        # полнотекстовый поиск по ILIKE '%...%' (расширение pg_trgm)
        Index("ix_incoming_documents_summary_trgm", "summary", postgresql_using="gin",
              postgresql_ops={"summary": "gin_trgm_ops"}),
    )

    registration_number: Mapped[str] = mapped_column(String(64), unique=True)
    received_date: Mapped[date] = mapped_column(Date, index=True)
    registration_date: Mapped[date] = mapped_column(Date, index=True)
    correspondent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("correspondents.id", ondelete="RESTRICT"), index=True)
    addressee: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    document_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_types.id", ondelete="RESTRICT"), index=True)
    page_count: Mapped[int] = mapped_column(Integer)
    execution_deadline: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[DocumentStatus] = mapped_column(_enum(DocumentStatus), default=DocumentStatus.REGISTERED,
                                                   index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    correspondent: Mapped[Correspondent] = relationship(lazy="selectin")
    document_type: Mapped[DocumentType] = relationship(lazy="selectin")
    resolutions: Mapped[list["Resolution"]] = relationship(lazy="selectin", order_by="Resolution.created_at")
    attachments: Mapped[list["Attachment"]] = relationship(lazy="raise", order_by="Attachment.created_at")
    history: Mapped[list["DocumentHistory"]] = relationship(
        lazy="raise", order_by="[DocumentHistory.created_at, DocumentHistory.seq]")


class Resolution(UUIDPk, Timestamps, Base):
    __tablename__ = "resolutions"
    __table_args__ = (CheckConstraint(_in("status", ResolutionStatus), name="status_valid"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incoming_documents.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    assigned_executor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    deadline: Mapped[date] = mapped_column(Date)
    status: Mapped[ResolutionStatus] = mapped_column(_enum(ResolutionStatus),
                                                     default=ResolutionStatus.IN_PROGRESS, index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User] = relationship(foreign_keys="Resolution.author_id", lazy="selectin")
    assigned_executor: Mapped[User] = relationship(foreign_keys="Resolution.assigned_executor_id",
                                                   lazy="selectin")


class Attachment(UUIDPk, Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        CheckConstraint(_in("attachment_type", AttachmentType), name="type_valid"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incoming_documents.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    attachment_type: Mapped[AttachmentType] = mapped_column(_enum(AttachmentType), default=AttachmentType.OTHER)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 server_default=func.now())

    uploader: Mapped[User] = relationship(lazy="selectin")


class DocumentHistory(UUIDPk, Base):
    """Журнал действий по карточке. Через API не редактируется и не удаляется."""

    __tablename__ = "document_history"
    __table_args__ = (
        CheckConstraint(f"old_status IS NULL OR {_in('old_status', DocumentStatus)}", name="old_status_valid"),
        CheckConstraint(f"new_status IS NULL OR {_in('new_status', DocumentStatus)}", name="new_status_valid"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incoming_documents.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(64))
    old_status: Mapped[DocumentStatus | None] = mapped_column(_enum(DocumentStatus))
    new_status: Mapped[DocumentStatus | None] = mapped_column(_enum(DocumentStatus))
    comment: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                 server_default=func.now())
    # монотонный порядковый номер: стабильный порядок записей, созданных в одной транзакции
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)

    user: Mapped[User] = relationship(lazy="selectin")

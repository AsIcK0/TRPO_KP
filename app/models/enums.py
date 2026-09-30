"""Доменные перечисления. Модуль намеренно не зависит от SQLAlchemy/FastAPI."""

from enum import StrEnum


class Role(StrEnum):
    CLERK = "clerk"        # делопроизводитель
    MANAGER = "manager"    # руководитель
    EXECUTOR = "executor"  # исполнитель
    ADMIN = "admin"        # администратор


class DocumentStatus(StrEnum):
    REGISTERED = "зарегистрирован"
    UNDER_REVIEW = "на рассмотрении"
    IN_EXECUTION = "на исполнении"
    EXECUTED = "исполнен"
    REMOVED_FROM_CONTROL = "снят с контроля"
    ARCHIVED = "в архиве"


class ResolutionStatus(StrEnum):
    IN_PROGRESS = "на исполнении"
    EXECUTED = "исполнена"


class AttachmentType(StrEnum):
    SOURCE_SCAN = "source_scan"
    EXECUTION_REPORT = "execution_report"
    OTHER = "other"

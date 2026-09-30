"""Контроль сроков исполнения (чистые функции)."""

from datetime import date, datetime
from enum import StrEnum

from app.models.enums import DocumentStatus
from app.services.workflow import CLOSED_STATUSES


class DeadlineState(StrEnum):
    OK = "ok"              # срок не близок
    WARNING = "warning"    # срок наступает в ближайшие DEADLINE_WARNING_DAYS дней
    OVERDUE = "overdue"    # срок истек, документ не исполнен
    CLOSED = "closed"      # документ исполнен / снят с контроля / в архиве


def business_now() -> datetime:
    """Текущий момент в часовом поясе организации (APP_TIMEZONE)."""
    from app.core.config import get_settings  # ленивый импорт: модуль остается чистым для unit-тестов

    return datetime.now(get_settings().timezone)


def business_today() -> date:
    """«Сегодня» в часовом поясе организации: дата регистрации и контроль сроков."""
    return business_now().date()


def deadline_state(deadline: date, status: DocumentStatus, today: date, warning_days: int) -> DeadlineState:
    if status in CLOSED_STATUSES:
        return DeadlineState.CLOSED
    if deadline < today:
        return DeadlineState.OVERDUE
    if (deadline - today).days <= warning_days:
        return DeadlineState.WARNING
    return DeadlineState.OK


def days_left(deadline: date, today: date) -> int:
    """Оставшиеся дни; отрицательное значение — просрочка."""
    return (deadline - today).days

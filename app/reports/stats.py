"""Расчет показателей для отчетов (чистые функции, без обращения к БД)."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.models.enums import DocumentStatus
from app.services.workflow import CLOSED_STATUSES


@dataclass(frozen=True)
class ResolutionFact:
    executor_id: str
    executor_name: str
    document_id: str
    created_at: datetime
    executed_at: datetime | None
    deadline: date


@dataclass(frozen=True)
class ExecutorStat:
    executor_name: str
    documents: int
    resolutions: int
    executed: int
    overdue: int
    avg_days: float | None
    overdue_pct: float


def is_resolution_overdue(fact: ResolutionFact, today: date) -> bool:
    if fact.executed_at is not None:
        return fact.executed_at.date() > fact.deadline
    return fact.deadline < today


def compute_executor_stats(facts: list[ResolutionFact], today: date) -> list[ExecutorStat]:
    grouped: dict[str, list[ResolutionFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.executor_id, []).append(fact)

    stats: list[ExecutorStat] = []
    for items in grouped.values():
        done = [f for f in items if f.executed_at is not None]
        durations = [(f.executed_at - f.created_at).total_seconds() / 86400 for f in done if f.executed_at]
        overdue = sum(1 for f in items if is_resolution_overdue(f, today))
        stats.append(ExecutorStat(
            executor_name=items[0].executor_name,
            documents=len({f.document_id for f in items}),
            resolutions=len(items),
            executed=len(done),
            overdue=overdue,
            avg_days=round(sum(durations) / len(durations), 1) if durations else None,
            overdue_pct=round(overdue * 100 / len(items), 1),
        ))
    return sorted(stats, key=lambda s: s.executor_name)


class DeadlineCategory(StrEnum):
    ON_TIME = "Исполнен в срок"
    LATE = "Исполнен с просрочкой"
    OVERDUE = "Просрочен, не исполнен"
    IN_PROGRESS = "В работе, срок не наступил"
    UNKNOWN = "Закрыт, дата исполнения не зафиксирована"


def classify_deadline(deadline: date, status: DocumentStatus, executed_date: date | None,
                      today: date) -> tuple[DeadlineCategory, int | None]:
    """Категория исполнения и отклонение от срока в днях (>0 — просрочка, <0 — раньше срока)."""
    if status in CLOSED_STATUSES:
        if executed_date is None:
            return DeadlineCategory.UNKNOWN, None
        deviation = (executed_date - deadline).days
        return (DeadlineCategory.ON_TIME if deviation <= 0 else DeadlineCategory.LATE), deviation
    if deadline < today:
        return DeadlineCategory.OVERDUE, (today - deadline).days
    return DeadlineCategory.IN_PROGRESS, None

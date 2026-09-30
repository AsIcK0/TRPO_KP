"""Централизованная машина состояний карточки документа.

Единственное место, где описаны допустимые переходы статусов и роли,
которым эти переходы разрешены.
"""

from app.models.enums import DocumentStatus as S
from app.models.enums import Role

# (старый статус, новый статус) -> роли, которым разрешен переход
TRANSITIONS: dict[tuple[S, S], frozenset[Role]] = {
    (S.REGISTERED, S.UNDER_REVIEW): frozenset({Role.CLERK}),
    # переход выполняется автоматически при создании резолюции руководителем
    (S.UNDER_REVIEW, S.IN_EXECUTION): frozenset({Role.MANAGER}),
    (S.IN_EXECUTION, S.EXECUTED): frozenset({Role.EXECUTOR}),
    (S.EXECUTED, S.REMOVED_FROM_CONTROL): frozenset({Role.CLERK}),
    (S.REMOVED_FROM_CONTROL, S.ARCHIVED): frozenset({Role.CLERK}),
}
# аннулирование: из любого статуса обратно в «зарегистрирован» — только администратор
for _status in S:
    if _status is not S.REGISTERED:
        TRANSITIONS[(_status, S.REGISTERED)] = frozenset({Role.ADMIN})

# статусы, в которых срок исполнения уже не контролируется
CLOSED_STATUSES: frozenset[S] = frozenset({S.EXECUTED, S.REMOVED_FROM_CONTROL, S.ARCHIVED})

# статусы, в которых резолюции можно создавать и редактировать
RESOLUTION_OPEN_STATUSES: frozenset[S] = frozenset({S.UNDER_REVIEW, S.IN_EXECUTION})


def transition_roles(old: S, new: S) -> frozenset[Role] | None:
    """Роли, которым разрешен переход; None — если переход вообще не существует."""
    return TRANSITIONS.get((old, new))


def is_transition_allowed(old: S, new: S) -> bool:
    return (old, new) in TRANSITIONS


def allowed_targets(old: S) -> list[S]:
    return [new for (o, new) in TRANSITIONS if o is old]

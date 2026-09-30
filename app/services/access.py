"""Контекстные ограничения доступа (сверх матрицы ролей)."""

from app.core.errors import ForbiddenError
from app.models.entities import IncomingDocument, User
from app.models.enums import Role


def is_assigned_to(actor: User, document: IncomingDocument) -> bool:
    return any(r.assigned_executor_id == actor.id for r in document.resolutions)


def assert_can_view_document(actor: User, document: IncomingDocument) -> None:
    """Исполнитель видит только документы, по которым ему назначены резолюции."""
    if actor.role == Role.EXECUTOR and not is_assigned_to(actor, document):
        raise ForbiddenError("Документ не назначен вам на исполнение", code="FORBIDDEN")

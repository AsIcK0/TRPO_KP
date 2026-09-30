"""Журналирование действий пользователей.

* История карточки (DocumentHistory) — в БД, транзакционно вместе с самим действием.
* Прочие операции (вход, отчеты, выгрузки, удаление) — структурированные записи в stdout.
"""

import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import DocumentHistory
from app.models.enums import DocumentStatus

audit_logger = logging.getLogger("app.audit")


def log_action(actor_id: uuid.UUID | str | None, action: str, **details: Any) -> None:
    audit_logger.info("action=%s actor=%s details=%s", action, actor_id,
                      json.dumps(details, default=str, ensure_ascii=False))


def jsonable(value: Any) -> Any:
    """Приводит значение к JSON-совместимому виду (даты, UUID, enum -> строки)."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class AuditRecorder:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def document_event(self, *, document_id: uuid.UUID, user_id: uuid.UUID, action: str,
                       old_status: DocumentStatus | None = None, new_status: DocumentStatus | None = None,
                       comment: str | None = None, meta: dict[str, Any] | None = None) -> DocumentHistory:
        entry = DocumentHistory(document_id=document_id, user_id=user_id, action=action,
                                old_status=old_status, new_status=new_status, comment=comment, meta=meta)
        self._session.add(entry)
        return entry

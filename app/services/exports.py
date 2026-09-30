"""Выгрузка журнала регистрации (CSV)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import log_action
from app.core.config import Settings
from app.models.entities import User
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentFilters
from app.schemas.report import RegistrationLogQuery
from app.services.deadlines import DeadlineState, business_today, deadline_state
from app.services.reports import fmt_date

HEADERS = ["Регистрационный номер", "Дата поступления", "Дата регистрации", "Корреспондент",
           "ИНН корреспондента", "Адресат", "Краткое содержание", "Тип документа", "Количество листов",
           "Срок исполнения", "Статус", "Исполнители", "Просрочен"]


class ExportService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.settings = settings
        self.docs = DocumentRepository(db)

    async def registration_log(self, actor: User, query: RegistrationLogQuery) -> tuple[list[str], list[list]]:
        today = business_today()
        warning_days = self.settings.deadline_warning_days
        filters = DocumentFilters(date_from=query.date_from, date_to=query.date_to,
                                  correspondent_id=query.correspondent_id, status=query.status,
                                  document_type_id=query.document_type_id)
        docs = await self.docs.search_all(filters, today=today, warning_days=warning_days)
        rows: list[list] = []
        for d in docs:
            state = deadline_state(d.execution_deadline, d.status, today, warning_days)
            executors = ", ".join(sorted({r.assigned_executor.full_name for r in d.resolutions}))
            rows.append([d.registration_number, fmt_date(d.received_date), fmt_date(d.registration_date),
                         d.correspondent.name, d.correspondent.inn or "", d.addressee or "",
                         " ".join(d.summary.split()), d.document_type.name, d.page_count,
                         fmt_date(d.execution_deadline), d.status.value, executors,
                         "да" if state == DeadlineState.OVERDUE else "нет"])
        log_action(actor.id, "registration_log_exported", rows=len(rows), date_from=query.date_from,
                   date_to=query.date_to)
        return HEADERS, rows

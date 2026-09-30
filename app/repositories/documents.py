import uuid
from datetime import date, timedelta

from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Correspondent, IncomingDocument, RegistrationCounter, Resolution
from app.repositories.common import LIKE_ESCAPE, like_pattern
from app.schemas.document import DocumentFilters
from app.services.deadlines import DeadlineState
from app.services.workflow import CLOSED_STATUSES

D = IncomingDocument
_SORT_COLUMNS = {
    "registration_number": D.registration_number,
    "received_date": D.received_date,
    "registration_date": D.registration_date,
    "execution_deadline": D.execution_deadline,
    "status": D.status,
    "created_at": D.created_at,
}


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- чтение -------------------------------------------------------------------------------
    async def get(self, document_id: uuid.UUID, *, detail: bool = False) -> D | None:
        stmt = select(D).where(D.id == document_id).execution_options(populate_existing=True)
        if detail:
            stmt = stmt.options(selectinload(D.attachments), selectinload(D.history))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_number(self, registration_number: str, *, detail: bool = False) -> D | None:
        stmt = select(D).where(D.registration_number == registration_number).execution_options(
            populate_existing=True)
        if detail:
            stmt = stmt.options(selectinload(D.attachments), selectinload(D.history))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def lock(self, document_id: uuid.UUID) -> bool:
        """Блокировка строки документа (SELECT ... FOR UPDATE) на время транзакции."""
        stmt = select(D.id).where(D.id == document_id).with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    # --- запись -------------------------------------------------------------------------------
    def add(self, document: D) -> None:
        self.session.add(document)

    async def delete(self, document_id: uuid.UUID) -> None:
        # дочерние записи (резолюции, вложения, история) удаляются каскадом на уровне БД
        await self.session.execute(delete(D).where(D.id == document_id))

    async def next_sequence(self, counter_key: int) -> int:
        """Атомарный инкремент счетчика: INSERT .. ON CONFLICT DO UPDATE блокирует строку счетчика
        до конца транзакции, поэтому параллельные регистрации получают разные номера без гонок."""
        stmt = (pg_insert(RegistrationCounter)
                .values(year=counter_key, last_value=1)
                .on_conflict_do_update(index_elements=[RegistrationCounter.year],
                                       set_={"last_value": RegistrationCounter.last_value + 1})
                .returning(RegistrationCounter.last_value))
        return (await self.session.execute(stmt)).scalar_one()

    # --- поиск --------------------------------------------------------------------------------
    @staticmethod
    def _clauses(f: DocumentFilters, *, executor_scope: uuid.UUID | None, today: date, warning_days: int) -> list:
        clauses = []
        if executor_scope is not None:
            clauses.append(D.id.in_(select(Resolution.document_id).where(
                Resolution.assigned_executor_id == executor_scope)))
        if f.registration_number:
            clauses.append(D.registration_number.ilike(like_pattern(f.registration_number), escape=LIKE_ESCAPE))
        if f.date_from:
            clauses.append(D.registration_date >= f.date_from)
        if f.date_to:
            clauses.append(D.registration_date <= f.date_to)
        if f.correspondent_id:
            clauses.append(D.correspondent_id == f.correspondent_id)
        if f.executor_id:
            clauses.append(D.id.in_(select(Resolution.document_id).where(
                Resolution.assigned_executor_id == f.executor_id)))
        if f.status:
            clauses.append(D.status == f.status)
        if f.document_type_id:
            clauses.append(D.document_type_id == f.document_type_id)
        if f.search:
            pattern = like_pattern(f.search)
            clauses.append(or_(
                D.summary.ilike(pattern, escape=LIKE_ESCAPE),
                D.addressee.ilike(pattern, escape=LIKE_ESCAPE),
                D.registration_number.ilike(pattern, escape=LIKE_ESCAPE),
                D.correspondent_id.in_(select(Correspondent.id).where(
                    Correspondent.name.ilike(pattern, escape=LIKE_ESCAPE))),
            ))
        if f.deadline_state is not None:
            open_only = D.status.not_in(list(CLOSED_STATUSES))
            if f.deadline_state == DeadlineState.OVERDUE:
                clauses.append(and_(open_only, D.execution_deadline < today))
            elif f.deadline_state == DeadlineState.WARNING:
                clauses.append(and_(open_only, D.execution_deadline >= today,
                                    D.execution_deadline <= today + timedelta(days=warning_days)))
        return clauses

    @staticmethod
    def _order_by(sort: str) -> list:
        order = []
        for token in sort.split(","):
            token = token.strip()
            column = _SORT_COLUMNS[token.lstrip("-")]
            order.append(desc(column) if token.startswith("-") else column)
        order.extend([desc(D.created_at), D.id])  # стабильный порядок для пагинации
        return order

    async def search(self, f: DocumentFilters, *, executor_scope: uuid.UUID | None, today: date,
                     warning_days: int) -> tuple[list[D], int]:
        clauses = self._clauses(f, executor_scope=executor_scope, today=today, warning_days=warning_days)
        total = (await self.session.execute(select(func.count(D.id)).where(*clauses))).scalar_one()
        stmt = (select(D).where(*clauses).order_by(*self._order_by(f.sort))
                .limit(f.page_size).offset((f.page - 1) * f.page_size))
        return list((await self.session.execute(stmt)).scalars().all()), total

    async def search_all(self, f: DocumentFilters, *, today: date, warning_days: int) -> list[D]:
        """Все документы по фильтрам без пагинации (отчеты и выгрузки)."""
        clauses = self._clauses(f, executor_scope=None, today=today, warning_days=warning_days)
        stmt = select(D).where(*clauses).order_by(D.registration_date, D.registration_number)
        return list((await self.session.execute(stmt)).scalars().all())

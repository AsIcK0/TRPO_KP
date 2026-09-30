"""Формирование PDF-отчетов: данные берутся из БД, расчеты — в app/reports/stats.py."""

import asyncio
import logging
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import log_action
from app.core.config import Settings
from app.models.entities import IncomingDocument, User
from app.repositories.correspondents import CorrespondentRepository
from app.repositories.dictionaries import DocumentTypeRepository
from app.repositories.documents import DocumentRepository
from app.repositories.history import HistoryRepository
from app.repositories.resolutions import ResolutionRepository
from app.repositories.users import UserRepository
from app.reports.pdf import ReportData, render_report
from app.reports.stats import DeadlineCategory, ResolutionFact, classify_deadline, compute_executor_stats
from app.schemas.document import DocumentFilters
from app.schemas.report import ReportRequest, ReportType
from app.services.deadlines import DeadlineState, business_now, business_today, deadline_state

logger = logging.getLogger(__name__)

ROLE_LABELS = {"clerk": "делопроизводитель", "manager": "руководитель", "executor": "исполнитель",
               "admin": "администратор"}
TITLES = {
    ReportType.DOCUMENTS: "Отчет по входящим документам",
    ReportType.EXECUTORS: "Отчет по исполнителям",
    ReportType.DEADLINES: "Отчет по срокам исполнения",
}


def fmt_date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "—"


def _shorten(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _executor_names(doc: IncomingDocument) -> str:
    names = {r.assigned_executor.full_name for r in doc.resolutions}
    return ", ".join(sorted(names)) or "—"


class ReportService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.settings = settings
        self.docs = DocumentRepository(db)
        self.resolutions = ResolutionRepository(db)
        self.history = HistoryRepository(db)
        self.correspondents = CorrespondentRepository(db)
        self.types = DocumentTypeRepository(db)
        self.users = UserRepository(db)

    async def _filter_labels(self, req: ReportRequest) -> list[str]:
        labels: list[str] = []
        if req.correspondent_id:
            c = await self.correspondents.get(req.correspondent_id)
            labels.append(f"корреспондент: {c.name if c else req.correspondent_id}")
        if req.executor_id:
            u = await self.users.get(req.executor_id)
            labels.append(f"исполнитель: {u.full_name if u else req.executor_id}")
        if req.status:
            labels.append(f"статус: {req.status.value}")
        if req.document_type_id:
            t = await self.types.get(req.document_type_id)
            labels.append(f"тип документа: {t.name if t else req.document_type_id}")
        return labels

    async def generate(self, actor: User, req: ReportRequest) -> tuple[bytes, str]:
        today = business_today()
        warning_days = self.settings.deadline_warning_days
        filters = DocumentFilters(date_from=req.period_from, date_to=req.period_to,
                                  correspondent_id=req.correspondent_id, executor_id=req.executor_id,
                                  status=req.status, document_type_id=req.document_type_id)
        data = ReportData(
            title=TITLES[req.report_type],
            period=f"{fmt_date(req.period_from)} — {fmt_date(req.period_to)} (по дате регистрации)",
            generated_at=business_now(),
            generated_by=f"{actor.full_name} ({ROLE_LABELS.get(actor.role.value, '')})",
            filters=await self._filter_labels(req), columns=[], col_weights=[], rows=[])

        if req.report_type == ReportType.DOCUMENTS:
            docs = await self.docs.search_all(filters, today=today, warning_days=warning_days)
            self._fill_documents(data, docs, today, warning_days)
        elif req.report_type == ReportType.EXECUTORS:
            await self._fill_executors(data, req, today)
        else:
            docs = await self.docs.search_all(filters, today=today, warning_days=warning_days)
            await self._fill_deadlines(data, docs, today)

        pdf = await asyncio.to_thread(render_report, data, self.settings.pdf_font_path)
        filename = f"report-{req.report_type.value}-{req.period_from}_{req.period_to}.pdf"
        log_action(actor.id, "report_generated", type=req.report_type, period_from=req.period_from,
                   period_to=req.period_to, rows=len(data.rows))
        return pdf, filename

    # --- по документам -------------------------------------------------------------------------
    @staticmethod
    def _fill_documents(data: ReportData, docs: list[IncomingDocument], today, warning_days: int) -> None:
        data.columns = ["Рег. номер", "Дата рег.", "Корреспондент", "Тип", "Краткое содержание", "Срок",
                        "Статус", "Исполнители"]
        data.col_weights = [1.7, 1.1, 2.2, 1.5, 4.2, 1.1, 1.5, 2.2]
        by_status: Counter[str] = Counter()
        overdue = warning = 0
        for d in docs:
            state = deadline_state(d.execution_deadline, d.status, today, warning_days)
            overdue += state == DeadlineState.OVERDUE
            warning += state == DeadlineState.WARNING
            by_status[d.status.value] += 1
            status_text = d.status.value + (" (просрочен)" if state == DeadlineState.OVERDUE else "")
            data.rows.append([d.registration_number, fmt_date(d.registration_date), d.correspondent.name,
                              d.document_type.name, _shorten(d.summary), fmt_date(d.execution_deadline),
                              status_text, _executor_names(d)])
        data.summary = [("Всего документов", str(len(docs)))]
        data.summary += [(f"Статус «{s}»", str(n)) for s, n in by_status.items()]
        data.summary += [("Просрочено", str(overdue)), ("Срок наступает в ближайшие "
                                                        f"{warning_days} дн.", str(warning))]

    # --- по исполнителям -----------------------------------------------------------------------
    async def _fill_executors(self, data: ReportData, req: ReportRequest, today) -> None:
        resolutions = await self.resolutions.for_report(
            date_from=req.period_from, date_to=req.period_to, executor_id=req.executor_id,
            correspondent_id=req.correspondent_id, status=req.status, document_type_id=req.document_type_id)
        tz = self.settings.timezone
        facts = [ResolutionFact(executor_id=str(r.assigned_executor_id),
                                executor_name=r.assigned_executor.full_name, document_id=str(r.document_id),
                                created_at=r.created_at.astimezone(tz),
                                executed_at=r.executed_at.astimezone(tz) if r.executed_at else None,
                                deadline=r.deadline)
                 for r in resolutions]
        stats = compute_executor_stats(facts, today)
        data.columns = ["ФИО исполнителя", "Документов", "Резолюций", "Исполнено", "Средний срок исполнения, дн.",
                        "Просрочено", "Доля просрочки, %"]
        data.col_weights = [4, 1.3, 1.3, 1.3, 2, 1.3, 1.6]
        for s in stats:
            data.rows.append([s.executor_name, str(s.documents), str(s.resolutions), str(s.executed),
                              "—" if s.avg_days is None else f"{s.avg_days:.1f}", str(s.overdue),
                              f"{s.overdue_pct:.1f}"])
        total = sum(s.resolutions for s in stats)
        overdue = sum(s.overdue for s in stats)
        data.summary = [("Исполнителей", str(len(stats))), ("Резолюций всего", str(total)),
                        ("Из них просрочено", str(overdue)),
                        ("Общая доля просрочки, %", f"{(overdue * 100 / total):.1f}" if total else "0.0")]

    # --- по срокам исполнения ------------------------------------------------------------------
    async def _fill_deadlines(self, data: ReportData, docs: list[IncomingDocument], today) -> None:
        tz = self.settings.timezone
        moments = await self.history.executed_moments([d.id for d in docs])
        executed = {doc_id: moment.astimezone(tz).date() for doc_id, moment in moments.items()}
        data.columns = ["Рег. номер", "Корреспондент", "Срок исполнения", "Фактическая дата исполнения",
                        "Результат", "Отклонение, дн."]
        data.col_weights = [1.8, 3, 1.5, 1.8, 3, 1.4]
        counts: Counter[DeadlineCategory] = Counter()
        for d in docs:
            category, deviation = classify_deadline(d.execution_deadline, d.status, executed.get(d.id), today)
            counts[category] += 1
            deviation_text = "—" if deviation is None else f"{deviation:+d}"
            is_done = category in (DeadlineCategory.ON_TIME, DeadlineCategory.LATE)
            fact_date = fmt_date(executed.get(d.id)) if is_done else "—"
            data.rows.append([d.registration_number, d.correspondent.name, fmt_date(d.execution_deadline),
                              fact_date, category.value, deviation_text])
        data.summary = [("Всего документов", str(len(docs)))]
        data.summary += [(c.value, str(counts[c])) for c in DeadlineCategory if counts[c]]
        done = counts[DeadlineCategory.ON_TIME] + counts[DeadlineCategory.LATE]
        if done:
            data.summary.append(("Доля исполненных в срок, %",
                                 f"{counts[DeadlineCategory.ON_TIME] * 100 / done:.1f}"))

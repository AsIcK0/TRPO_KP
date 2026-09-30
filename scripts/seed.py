"""Заполнение БД демонстрационными данными (все персональные данные вымышленные).

Запуск:  python -m scripts.seed          (в контейнере: docker compose exec backend python -m scripts.seed)
Повторный запуск безопасен: если пользователи уже есть, скрипт ничего не меняет.
"""

import asyncio
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import get_engine, get_sessionmaker
from app.models.entities import (
    Correspondent,
    Department,
    DocumentHistory,
    DocumentType,
    IncomingDocument,
    Position,
    Resolution,
    User,
)
from app.models.enums import DocumentStatus as S
from app.models.enums import ResolutionStatus, Role
from app.repositories.documents import DocumentRepository
from app.security.passwords import hash_password
from app.services.deadlines import business_today
from app.services.reg_number import counter_key, format_registration_number

DEPARTMENTS = ["Канцелярия", "Юридический отдел", "Финансово-экономический отдел"]
POSITIONS = ["Начальник канцелярии", "Делопроизводитель", "Директор", "Главный юрист", "Ведущий специалист"]
DOCUMENT_TYPES = ["Письмо", "Запрос", "Уведомление", "Распоряжение", "Договор", "Претензия",
                  "Обращение граждан", "Другое"]

# логин, пароль, роль, ФИО, подразделение, должность
USERS = [
    ("admin", "admin123", Role.ADMIN, "Романов Игорь Викторович", 0, 4),
    ("clerk", "clerk123", Role.CLERK, "Иванова Анна Сергеевна", 0, 1),
    ("manager", "manager123", Role.MANAGER, "Петров Алексей Николаевич", 0, 2),
    ("executor1", "executor123", Role.EXECUTOR, "Сидорова Мария Игоревна", 1, 3),
    ("executor2", "executor123", Role.EXECUTOR, "Козлов Дмитрий Андреевич", 2, 4),
]

CORRESPONDENTS = [
    ("ООО «Северный ветер»", "7701000001", "г. Москва, ул. Березовая, д. 1", "+7 495 100-00-01", "Кузнецов И. И."),
    ("АО «Прогресс-Инжиниринг»", "7702000002", "г. Санкт-Петербург, Невский пр., д. 10", "+7 812 100-00-02",
     "Орлова Т. А."),
    ("ИП Смирнов Олег Павлович", "770300000003", "г. Казань, ул. Кремлевская, д. 5", "+7 843 100-00-03",
     "Смирнов О. П."),
    ("Управление образования", "7704000004", "г. Тула, пл. Ленина, д. 3", "+7 487 100-00-04", "Белова Н. В."),
    ("ООО «Ромашка-Сервис»", "7705000005", "г. Екатеринбург, ул. Мира, д. 22", "+7 343 100-00-05", "Захаров П. Л."),
    ("ЗАО «ТехноСнаб»", "7706000006", "г. Самара, ул. Заводская, д. 7", "+7 846 100-00-06", "Волков А. Е."),
    ("Комитет по строительству", "7707000007", "г. Пермь, ул. Строителей, д. 12", "+7 342 100-00-07",
     "Мельникова Е. С."),
    ("НКО «Открытый диалог»", "7708000008", "г. Омск, ул. Партизанская, д. 4", "+7 381 100-00-08", "Тихонов В. Д."),
    ("ООО «Альфа-Логистик»", "7709000009", "г. Ростов-на-Дону, ул. Портовая, д. 9", "+7 863 100-00-09", "Гусева Л. Р."),
    ("Гражданин Никитин С. А.", None, "г. Воронеж, ул. Садовая, д. 15, кв. 8", "+7 473 100-00-10", "Никитин С. А."),
]

SUMMARIES = [
    "Уведомление о расторжении договора поставки", "Запрос сведений о ходе исполнения договора",
    "Претензия по качеству поставленного оборудования", "Обращение по вопросу благоустройства территории",
    "Приглашение на совещание по вопросам взаимодействия", "Письмо о продлении срока действия договора",
    "Запрос копий учредительных документов", "Уведомление об изменении банковских реквизитов",
    "Предложение о сотрудничестве в сфере логистики", "Претензия о нарушении сроков оказания услуг",
    "Обращение гражданина о рассмотрении жалобы", "Распоряжение о предоставлении отчетности",
    "Запрос информации об исполнении поручения", "Письмо о согласовании проектной документации",
    "Уведомление о проведении проверки", "Договор на оказание консультационных услуг (проект)",
    "Обращение по вопросу выдачи справки", "Запрос заключения по правовым вопросам закупки",
    "Письмо о приостановке платежей", "Предложение по актуализации регламента взаимодействия",
]

# порядок статусов по «зрелости» документа
_ORDER = [S.REGISTERED, S.UNDER_REVIEW, S.IN_EXECUTION, S.EXECUTED, S.REMOVED_FROM_CONTROL, S.ARCHIVED]


def status_for(i: int) -> S:
    if i <= 1:
        return S.ARCHIVED
    if i <= 3:
        return S.REMOVED_FROM_CONTROL
    if i <= 6:
        return S.EXECUTED
    if i <= 12:
        return S.IN_EXECUTION
    if i <= 15:
        return S.UNDER_REVIEW
    return S.REGISTERED


async def seed() -> None:
    settings = get_settings()
    today = business_today()
    async with get_sessionmaker()() as session:
        if (await session.execute(select(func.count(User.id)))).scalar_one() > 0:
            print("БД уже содержит данные — seed пропущен.")
            return

        departments = [Department(name=n) for n in DEPARTMENTS]
        positions = [Position(name=n) for n in POSITIONS]
        types = [DocumentType(name=n, is_active=True) for n in DOCUMENT_TYPES]
        session.add_all([*departments, *positions, *types])
        await session.flush()

        users: dict[str, User] = {}
        for login, password, role, full_name, dep, pos in USERS:
            users[login] = User(full_name=full_name, login=login, email=f"{login}@example.org",
                                password_hash=hash_password(password), role=role,
                                department_id=departments[dep].id, position_id=positions[pos].id, is_active=True)
        session.add_all(users.values())
        correspondents = [Correspondent(name=n, inn=inn, address=addr, phone=phone,
                                        email=f"office{idx}@example.org", signer_full_name=signer)
                          for idx, (n, inn, addr, phone, signer) in enumerate(CORRESPONDENTS, start=1)]
        session.add_all(correspondents)
        await session.flush()

        clerk, manager = users["clerk"], users["manager"]
        executors = [users["executor1"], users["executor2"]]
        repo = DocumentRepository(session)
        total = len(SUMMARIES)

        for i, summary in enumerate(SUMMARIES):
            status = status_for(i)
            reg_date = today - timedelta(days=2 * (total - 1 - i) + 1)
            base = datetime.combine(reg_date, time(9, 0), tzinfo=UTC)
            rank = _ORDER.index(status)

            if i == 7:
                deadline = today - timedelta(days=3)      # просрочен
            elif i == 8:
                deadline = today - timedelta(days=1)      # просрочен
            elif i == 9:
                deadline = today + timedelta(days=2)      # предупреждение о сроке
            elif status in (S.ARCHIVED, S.REMOVED_FROM_CONTROL, S.EXECUTED):
                deadline = reg_date + timedelta(days=14)
            else:
                deadline = today + timedelta(days=10 + i)

            executed_at = base + timedelta(days=5 + i % 4)
            archived_at = executed_at + timedelta(days=2) if status == S.ARCHIVED else None

            sequence = await repo.next_sequence(counter_key(settings.reg_number_template, reg_date.year))
            document = IncomingDocument(
                registration_number=format_registration_number(settings.reg_number_template, reg_date.year, sequence),
                received_date=reg_date - timedelta(days=i % 3), registration_date=reg_date,
                correspondent_id=correspondents[i % len(correspondents)].id,
                addressee="Директору" if i % 2 == 0 else "Главному юристу", summary=summary,
                document_type_id=types[i % len(types)].id, page_count=1 + (i * 3) % 12,
                execution_deadline=deadline, status=status, created_by=clerk.id, archived_at=archived_at,
                created_at=base, updated_at=base)
            session.add(document)
            await session.flush()

            def log(action: str, user: User, at: datetime, old: S | None = None, new: S | None = None,
                    comment: str | None = None, meta: dict | None = None, doc=document) -> None:
                session.add(DocumentHistory(document_id=doc.id, user_id=user.id, action=action, old_status=old,
                                            new_status=new, comment=comment, meta=meta, created_at=at))

            log("document_registered", clerk, base, new=S.REGISTERED,
                meta={"registration_number": document.registration_number})
            if rank >= 1:
                log("status_changed", clerk, base + timedelta(hours=2), S.REGISTERED, S.UNDER_REVIEW,
                    "Передано руководителю")
            if rank >= 2:
                assigned = executors if i in (8, 11) else [executors[i % 2]]  # у части документов две резолюции
                created_at = base + timedelta(days=1)
                resolutions = []
                for k, executor in enumerate(assigned):
                    done = rank >= 3 or (i == 8 and k == 0)  # у документа №8 исполнена только первая резолюция
                    resolution = Resolution(
                        document_id=document.id,
                        text=f"Рассмотреть и подготовить ответ. Исполнитель: {executor.full_name}",
                        author_id=manager.id, assigned_executor_id=executor.id,
                        deadline=min(deadline, reg_date + timedelta(days=14)) if rank >= 3 else deadline,
                        status=ResolutionStatus.EXECUTED if done else ResolutionStatus.IN_PROGRESS,
                        executed_at=executed_at if done else None, created_at=created_at, updated_at=created_at)
                    session.add(resolution)
                    resolutions.append((resolution, executor, done))
                await session.flush()
                for resolution, executor, _done in resolutions:
                    log("resolution_created", manager, created_at,
                        meta={"resolution_id": str(resolution.id), "executor_id": str(executor.id)})
                log("status_changed", manager, created_at, S.UNDER_REVIEW, S.IN_EXECUTION, "Создана резолюция")
                for resolution, executor, done in resolutions:
                    if done:
                        log("resolution_executed", executor, executed_at, comment="Исполнено, отчет подготовлен",
                            meta={"resolution_ids": [str(resolution.id)]})
                if rank >= 3:
                    log("status_changed", assigned[0], executed_at, S.IN_EXECUTION, S.EXECUTED,
                        "Поручение исполнено")
                if rank >= 4:
                    log("status_changed", clerk, executed_at + timedelta(days=1), S.EXECUTED,
                        S.REMOVED_FROM_CONTROL, "Снято с контроля")
                if rank >= 5 and archived_at is not None:
                    log("status_changed", clerk, archived_at, S.REMOVED_FROM_CONTROL, S.ARCHIVED, "Передано в архив")

        await session.commit()
        print(f"Готово: {len(users)} пользователей, {len(correspondents)} корреспондентов, {total} документов.")


async def main() -> None:
    try:
        await seed()
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())

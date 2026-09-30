"""Seed-данные: состав, согласованность истории со статусами, рабочие учетные записи."""

from collections import Counter

import httpx
from sqlalchemy import func, select, text

from app.db.session import get_sessionmaker
from app.main import app
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
from app.models.enums import DocumentStatus
from scripts.seed import seed
from tests.integration.conftest import TABLES


async def test_seed_creates_consistent_demo_data(storage_ready):
    async with get_sessionmaker()() as session:
        await session.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        await session.commit()
    await seed()
    await seed()  # повторный запуск ничего не дублирует

    async with get_sessionmaker()() as session:
        async def count(model) -> int:
            return (await session.execute(select(func.count()).select_from(model))).scalar_one()

        assert (await count(User), await count(Department), await count(Position)) == (5, 3, 5)
        assert (await count(DocumentType), await count(Correspondent), await count(IncomingDocument)) == (8, 10, 20)
        assert await count(Resolution) > 0

        docs = (await session.execute(select(IncomingDocument))).scalars().all()
        assert set(Counter(d.status for d in docs)) == set(DocumentStatus)  # все статусы представлены
        assert len({d.registration_number for d in docs}) == 20
        history = (await session.execute(
            select(DocumentHistory).order_by(DocumentHistory.created_at, DocumentHistory.seq))).scalars().all()
        last_status = {}
        for entry in history:
            if entry.new_status is not None:
                last_status[entry.document_id] = entry.new_status
        # история не «фальшивая»: последний зафиксированный статус совпадает с текущим статусом документа
        assert all(last_status[d.id] == d.status for d in docs)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        for login, password in (("admin", "admin123"), ("clerk", "clerk123"), ("manager", "manager123"),
                                ("executor1", "executor123"), ("executor2", "executor123")):
            response = await client.post("/api/v1/auth/login", json={"login": login, "password": password})
            assert response.status_code == 200, (login, response.text)

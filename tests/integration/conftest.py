"""Инфраструктура интеграционных тестов: реальные PostgreSQL и MinIO (docker compose)."""

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine, get_sessionmaker
from app.main import app
from app.models.entities import Correspondent, Department, DocumentType, Position, User
from app.models.enums import Role
from app.security.passwords import hash_password
from app.security.tokens import create_access_token
from app.services.deadlines import business_today
from app.storage.s3 import get_storage
from tests.conftest import ROOT

TABLES = ("document_history, attachments, resolutions, incoming_documents, registration_counters, "
          "correspondents, users, document_types, positions, departments")

USERS = {
    "admin": (Role.ADMIN, "admin123", "Романов Игорь Викторович"),
    "clerk": (Role.CLERK, "clerk123", "Иванова Анна Сергеевна"),
    "manager": (Role.MANAGER, "manager123", "Петров Алексей Николаевич"),
    "executor1": (Role.EXECUTOR, "executor123", "Сидорова Мария Игоревна"),
    "executor2": (Role.EXECUTOR, "executor123", "Козлов Дмитрий Андреевич"),
}

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, env=dict(os.environ), check=True)


@pytest.fixture(scope="session")
def migrated_db() -> None:
    """Создает тестовую БД и прогоняет миграции вниз и вверх (проверка upgrade и downgrade)."""
    _run("-m", "tests.bootstrap_db")
    _run("-m", "alembic", "downgrade", "base")
    _run("-m", "alembic", "upgrade", "head")


@pytest.fixture(scope="session")
def password_hashes() -> dict[str, str]:
    return {pwd: hash_password(pwd) for _, pwd, _ in USERS.values()}


@pytest_asyncio.fixture(scope="session")
async def storage_ready(migrated_db):
    storage = get_storage()
    await storage.ensure_bucket()
    yield storage
    await get_engine().dispose()


@dataclass
class Ctx:
    client: httpx.AsyncClient
    users: dict[str, uuid.UUID]
    correspondents: list[uuid.UUID]
    doc_types: list[uuid.UUID]
    inactive_type: uuid.UUID
    department: uuid.UUID
    today: date = field(default_factory=business_today)

    def h(self, login: str) -> dict[str, str]:
        s = get_settings()
        token = create_access_token(user_id=self.users[login], secret=s.jwt_secret, algorithm=s.jwt_algorithm,
                                    expires_minutes=15)
        return {"Authorization": f"Bearer {token}"}

    # --- сценарные помощники (все действия идут через REST API) -------------------------------
    async def register(self, *, as_user: str = "clerk", **overrides) -> dict:
        payload = {
            "received_date": self.today.isoformat(),
            "correspondent_id": str(self.correspondents[0]),
            "addressee": "Директору",
            "summary": "Запрос сведений о ходе исполнения договора поставки",
            "document_type_id": str(self.doc_types[0]),
            "page_count": 3,
            "execution_deadline": (self.today + timedelta(days=10)).isoformat(),
        }
        payload.update({k: (str(v) if isinstance(v, (uuid.UUID, date)) else v) for k, v in overrides.items()})
        response = await self.client.post("/api/v1/incoming", json=payload, headers=self.h(as_user))
        assert response.status_code == 201, response.text
        return response.json()

    async def set_status(self, doc_id: str, status: str, *, as_user: str = "clerk",
                         comment: str | None = None) -> httpx.Response:
        return await self.client.post(f"/api/v1/incoming/{doc_id}/status", json={"status": status, "comment": comment},
                                      headers=self.h(as_user))

    async def to_review(self, doc_id: str) -> None:
        response = await self.set_status(doc_id, "на рассмотрении", comment="Передано руководителю")
        assert response.status_code == 200, response.text

    async def resolve(self, doc_id: str, executor: str = "executor1", *, days: int = 7) -> dict:
        response = await self.client.post(
            f"/api/v1/incoming/{doc_id}/resolutions", headers=self.h("manager"),
            json={"text": "Подготовить ответ", "assigned_executor_id": str(self.users[executor]),
                  "deadline": (self.today + timedelta(days=days)).isoformat()})
        assert response.status_code == 201, response.text
        return response.json()

    async def execute(self, doc_id: str, executor: str = "executor1") -> httpx.Response:
        return await self.set_status(doc_id, "исполнен", as_user=executor, comment="Ответ направлен")

    async def upload(self, doc_id: str, *, as_user: str, name: str = "скан.pdf", content: bytes = PDF_BYTES,
                     mime: str = "application/pdf", attachment_type: str | None = None) -> httpx.Response:
        data = {"attachment_type": attachment_type} if attachment_type else None
        return await self.client.post(f"/api/v1/incoming/{doc_id}/files", headers=self.h(as_user),
                                      files={"file": (name, content, mime)}, data=data)

    async def archived_document(self) -> dict:
        """Документ, проведенный через весь жизненный цикл до архива."""
        doc = await self.register()
        await self.to_review(doc["id"])
        await self.resolve(doc["id"])
        assert (await self.execute(doc["id"])).status_code == 200
        assert (await self.set_status(doc["id"], "снят с контроля")).status_code == 200
        response = await self.set_status(doc["id"], "в архиве")
        assert response.status_code == 200, response.text
        return response.json()

    async def sql(self, statement: str, **params) -> None:
        for key, value in params.items():
            if isinstance(value, str):
                try:
                    params[key] = uuid.UUID(value)
                except ValueError:
                    pass
        async with get_sessionmaker()() as session:
            await session.execute(text(statement), params)
            await session.commit()


@pytest_asyncio.fixture
async def ctx(storage_ready, password_hashes) -> Ctx:
    async with get_sessionmaker()() as session:
        await session.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        department = Department(name="Канцелярия")
        position = Position(name="Специалист")
        types = [DocumentType(name="Письмо"), DocumentType(name="Претензия")]
        inactive = DocumentType(name="Устаревший тип", is_active=False)
        session.add_all([department, position, *types, inactive])
        await session.flush()
        users = {login: User(full_name=name, login=login, email=f"{login}@example.org", role=role,
                             password_hash=password_hashes[pwd], department_id=department.id,
                             position_id=position.id, is_active=True)
                 for login, (role, pwd, name) in USERS.items()}
        correspondents = [
            Correspondent(name="ООО «Северный ветер»", inn="7701000001", signer_full_name="Кузнецов И. И."),
            Correspondent(name="АО «Прогресс-Инжиниринг»", inn="7702000002", signer_full_name="Орлова Т. А."),
        ]
        session.add_all([*users.values(), *correspondents])
        await session.commit()
        ids = {login: u.id for login, u in users.items()}
        corr_ids = [c.id for c in correspondents]
        type_ids = [t.id for t in types]
        inactive_id, department_id = inactive.id, department.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield Ctx(client=client, users=ids, correspondents=corr_ids, doc_types=type_ids,
                  inactive_type=inactive_id, department=department_id)


def assert_error(response: httpx.Response, status: int, code: str | None = None, field: str | None = None) -> dict:
    """Проверяет HTTP-код и единый формат ошибки {detail, code, field}."""
    assert response.status_code == status, response.text
    body = response.json()
    assert isinstance(body.get("detail"), str) and body["detail"], body
    assert isinstance(body.get("code"), str), body
    if code:
        assert body["code"] == code, body
    if field:
        assert body.get("field") == field, body
    return body

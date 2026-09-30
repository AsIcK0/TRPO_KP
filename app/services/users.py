import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import log_action
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.models.entities import User
from app.models.enums import Role
from app.repositories.dictionaries import DepartmentRepository, PositionRepository
from app.repositories.users import UserRepository
from app.schemas.common import make_page
from app.schemas.user import UserCreate, UserUpdate
from app.security.passwords import hash_password


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.departments = DepartmentRepository(db)
        self.positions = PositionRepository(db)

    async def _check_refs(self, department_id: uuid.UUID | None, position_id: uuid.UUID | None) -> None:
        if department_id is not None and await self.departments.get(department_id) is None:
            raise DomainValidationError("Подразделение не найдено", field="department_id")
        if position_id is not None and await self.positions.get(position_id) is None:
            raise DomainValidationError("Должность не найдена", field="position_id")

    async def create(self, actor: User, data: UserCreate) -> User:
        if await self.users.get_by_login(data.login):
            raise ConflictError("Пользователь с таким логином уже существует", code="LOGIN_CONFLICT", field="login")
        if await self.users.get_by_email(data.email):
            raise ConflictError("Пользователь с таким email уже существует", code="EMAIL_CONFLICT", field="email")
        await self._check_refs(data.department_id, data.position_id)

        user = User(full_name=data.full_name.strip(), login=data.login, email=data.email, role=data.role,
                    department_id=data.department_id, position_id=data.position_id, is_active=True,
                    password_hash=await asyncio.to_thread(hash_password, data.password))
        self.users.add(user)
        await self.db.commit()
        log_action(actor.id, "user_created", user_id=user.id, login=user.login, role=user.role)
        return await self._fresh(user.id)

    async def _fresh(self, user_id: uuid.UUID) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("Пользователь не найден")
        return user

    async def get(self, user_id: uuid.UUID) -> User:
        return await self._fresh(user_id)

    async def list_page(self, *, role: Role | None, is_active: bool | None, department_id: uuid.UUID | None,
                        search: str | None, page: int, page_size: int) -> dict:
        items, total = await self.users.list_page(role=role, is_active=is_active, department_id=department_id,
                                                  search=search, page=page, page_size=page_size)
        return make_page(items, total, page, page_size)

    async def list_executors(self) -> list[User]:
        return await self.users.list_active_executors()

    async def update(self, actor: User, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = await self._fresh(user_id)
        changes = data.model_dump(exclude_unset=True)
        for required in ("full_name", "email", "role", "department_id"):
            if required in changes and changes[required] is None:
                raise DomainValidationError("Поле не может быть пустым", field=required)

        if "email" in changes and changes["email"] != user.email:
            other = await self.users.get_by_email(changes["email"])
            if other and other.id != user.id:
                raise ConflictError("Пользователь с таким email уже существует", code="EMAIL_CONFLICT",
                                    field="email")
        if "role" in changes and user.id == actor.id and changes["role"] != Role.ADMIN:
            raise ConflictError("Нельзя лишить себя роли администратора", code="CANNOT_CHANGE_OWN_ROLE",
                                field="role")
        await self._check_refs(changes.get("department_id"), changes.get("position_id"))

        for key, value in changes.items():
            setattr(user, key, value.strip() if key == "full_name" else value)
        await self.db.commit()
        log_action(actor.id, "user_updated", user_id=user.id, fields=sorted(changes))
        return await self._fresh(user.id)

    async def deactivate(self, actor: User, user_id: uuid.UUID) -> User:
        user = await self._fresh(user_id)
        if user.id == actor.id:
            raise ConflictError("Нельзя деактивировать собственную учетную запись", code="CANNOT_DEACTIVATE_SELF")
        if user.is_active:
            user.is_active = False
            await self.db.commit()
            log_action(actor.id, "user_deactivated", user_id=user.id, login=user.login)
        return await self._fresh(user.id)

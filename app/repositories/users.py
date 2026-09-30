import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import User
from app.models.enums import Role
from app.repositories.common import LIKE_ESCAPE, like_pattern


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id).execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_login(self, login: str) -> User | None:
        return (await self.session.execute(select(User).where(User.login == login))).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()

    def add(self, user: User) -> None:
        self.session.add(user)

    async def list_page(self, *, role: Role | None, is_active: bool | None, department_id: uuid.UUID | None,
                   search: str | None, page: int, page_size: int) -> tuple[list[User], int]:
        clauses = []
        if role is not None:
            clauses.append(User.role == role)
        if is_active is not None:
            clauses.append(User.is_active == is_active)
        if department_id is not None:
            clauses.append(User.department_id == department_id)
        if search:
            pattern = like_pattern(search)
            clauses.append(or_(User.full_name.ilike(pattern, escape=LIKE_ESCAPE),
                               User.login.ilike(pattern, escape=LIKE_ESCAPE),
                               User.email.ilike(pattern, escape=LIKE_ESCAPE)))
        total = (await self.session.execute(select(func.count(User.id)).where(*clauses))).scalar_one()
        stmt = (select(User).where(*clauses).order_by(User.full_name, User.id)
                .limit(page_size).offset((page - 1) * page_size))
        return list((await self.session.execute(stmt)).scalars().all()), total

    async def list_active_executors(self) -> list[User]:
        stmt = select(User).where(User.role == Role.EXECUTOR, User.is_active.is_(True)).order_by(User.full_name)
        return list((await self.session.execute(stmt)).scalars().all())

"""Аутентификация и RBAC через Dependency Injection.

Каждый защищенный endpoint проверяет: валидность токена, существование и активность пользователя
(роль всегда читается из БД), разрешение роли. Контекстные ограничения — в сервисном слое.
"""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.dependencies.db import get_db
from app.models.entities import User
from app.repositories.users import UserRepository
from app.security.permissions import Permission, has_permission
from app.security.tokens import InvalidTokenError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False, description="JWT-токен, полученный в POST /api/v1/auth/login")


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
                           db: AsyncSession = Depends(get_db)) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Требуется аутентификация (заголовок Authorization: Bearer <token>)")
    settings = get_settings()
    try:
        user_id = decode_access_token(credentials.credentials, secret=settings.jwt_secret,
                                      algorithm=settings.jwt_algorithm)
    except InvalidTokenError:
        raise UnauthorizedError("Недействительный или просроченный токен", code="INVALID_TOKEN") from None
    user = await UserRepository(db).get(user_id)
    if user is None:
        raise UnauthorizedError("Пользователь не найден", code="INVALID_TOKEN")
    if not user.is_active:
        raise ForbiddenError("Учетная запись деактивирована", code="USER_INACTIVE")
    return user


def require_permission(*permissions: Permission, any_of: bool = False):
    """Фабрика зависимости: пропускает пользователя, если роль имеет все (или любое из) разрешений."""

    async def dependency(user: User = Depends(get_current_user)) -> User:
        checks = [has_permission(user.role, p) for p in permissions]
        if not (any(checks) if any_of else all(checks)):
            raise ForbiddenError("Недостаточно прав для выполнения операции", code="FORBIDDEN")
        return user

    return dependency

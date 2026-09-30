import asyncio
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import log_action
from app.core.config import Settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserOut
from app.security.passwords import hash_password, verify_password
from app.security.tokens import create_access_token


@lru_cache
def _dummy_hash() -> str:
    return hash_password("dummy-password-for-timing")


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self.users = UserRepository(db)
        self.settings = settings

    async def login(self, data: LoginRequest) -> TokenResponse:
        user = await self.users.get_by_login(data.login.strip())
        if user is None:
            await asyncio.to_thread(verify_password, data.password, _dummy_hash())  # выравниваем время ответа
            log_action(None, "login_failed", login=data.login)
            raise UnauthorizedError("Неверный логин или пароль", code="INVALID_CREDENTIALS")
        if not await asyncio.to_thread(verify_password, data.password, user.password_hash):
            log_action(user.id, "login_failed", login=data.login)
            raise UnauthorizedError("Неверный логин или пароль", code="INVALID_CREDENTIALS")
        if not user.is_active:
            log_action(user.id, "login_denied_inactive", login=data.login)
            raise ForbiddenError("Учетная запись деактивирована", code="USER_INACTIVE")

        s = self.settings
        token = create_access_token(user_id=user.id, secret=s.jwt_secret, algorithm=s.jwt_algorithm,
                                    expires_minutes=s.access_token_expire_minutes)
        log_action(user.id, "login", login=user.login)
        return TokenResponse(access_token=token, expires_in=s.access_token_expire_minutes * 60,
                             user=UserOut.model_validate(user))

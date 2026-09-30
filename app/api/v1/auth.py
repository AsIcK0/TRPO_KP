from fastapi import APIRouter, Depends

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import get_current_user
from app.dependencies.services import get_auth_service
from app.models.entities import User
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse
from app.schemas.common import ErrorResponse
from app.security.permissions import permissions_of
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login", response_model=TokenResponse, summary="Вход по логину и паролю",
    responses={401: {"model": ErrorResponse, "description": "Неверный логин или пароль (INVALID_CREDENTIALS)"},
               403: {"model": ErrorResponse, "description": "Учетная запись деактивирована (USER_INACTIVE)"}},
)
async def login(data: LoginRequest, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    """Возвращает JWT (передается в заголовке `Authorization: Bearer <token>`), данные пользователя и роль.
    Logout — удаление токена на клиенте (токен stateless)."""
    return await service.login(data)


@router.get("/me", response_model=MeResponse, summary="Текущий пользователь и его разрешения",
            responses={401: ERROR_RESPONSES[401], 403: ERROR_RESPONSES[403]})
async def me(user: User = Depends(get_current_user)) -> MeResponse:
    result = MeResponse.model_validate(user)
    result.permissions = permissions_of(user.role)
    return result

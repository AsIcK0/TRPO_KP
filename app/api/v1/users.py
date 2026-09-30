import uuid

from fastapi import APIRouter, Depends, Query

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import require_permission
from app.dependencies.services import get_user_service
from app.models.entities import User
from app.models.enums import Role
from app.schemas.common import Page
from app.schemas.user import ExecutorBrief, UserCreate, UserOut, UserUpdate
from app.security.permissions import Permission
from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"], responses=ERROR_RESPONSES)


@router.post("", response_model=UserOut, status_code=201, summary="Регистрация пользователя (admin)")
async def create_user(data: UserCreate, actor: User = Depends(require_permission(Permission.USER_CREATE)),
                      service: UserService = Depends(get_user_service)):
    return await service.create(actor, data)


@router.get("", response_model=Page[UserOut], summary="Список пользователей (admin)")
async def list_users(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), role: Role | None = None,
    is_active: bool | None = None, department_id: uuid.UUID | None = None,
    search: str | None = Query(None, max_length=200, description="ФИО, логин или email"),
    _: User = Depends(require_permission(Permission.USER_VIEW)),
    service: UserService = Depends(get_user_service),
):
    return await service.list_page(role=role, is_active=is_active, department_id=department_id, search=search,
                                   page=page, page_size=page_size)


@router.get("/executors", response_model=list[ExecutorBrief],
            summary="Активные исполнители (справочник для назначения резолюций)")
async def list_executors(
    _: User = Depends(require_permission(Permission.RESOLUTION_CREATE, Permission.USER_VIEW, any_of=True)),
    service: UserService = Depends(get_user_service),
):
    """Доступно руководителю и администратору: возвращает только id, ФИО и подразделение."""
    return await service.list_executors()


@router.get("/{user_id}", response_model=UserOut, summary="Профиль пользователя (admin)")
async def get_user(user_id: uuid.UUID, _: User = Depends(require_permission(Permission.USER_VIEW)),
                   service: UserService = Depends(get_user_service)):
    return await service.get(user_id)


@router.patch("/{user_id}", response_model=UserOut, summary="Редактирование пользователя (admin)")
async def update_user(user_id: uuid.UUID, data: UserUpdate,
                      actor: User = Depends(require_permission(Permission.USER_EDIT)),
                      service: UserService = Depends(get_user_service)):
    return await service.update(actor, user_id, data)


@router.post("/{user_id}/deactivate", response_model=UserOut,
             summary="Деактивация пользователя без физического удаления (admin)")
async def deactivate_user(user_id: uuid.UUID, actor: User = Depends(require_permission(Permission.USER_DEACTIVATE)),
                          service: UserService = Depends(get_user_service)):
    return await service.deactivate(actor, user_id)

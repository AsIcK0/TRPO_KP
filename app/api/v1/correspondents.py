import uuid

from fastapi import APIRouter, Depends, Query

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import require_permission
from app.dependencies.services import get_correspondent_service
from app.models.entities import User
from app.schemas.common import Page
from app.schemas.correspondent import CorrespondentCreate, CorrespondentOut, CorrespondentUpdate
from app.security.permissions import Permission
from app.services.correspondents import CorrespondentService

router = APIRouter(prefix="/correspondents", tags=["correspondents"], responses=ERROR_RESPONSES)


@router.post("", response_model=CorrespondentOut, status_code=201, summary="Создать корреспондента")
async def create_correspondent(data: CorrespondentCreate,
                               actor: User = Depends(require_permission(Permission.CORRESPONDENT_CREATE)),
                               service: CorrespondentService = Depends(get_correspondent_service)):
    return await service.create(actor, data)


@router.get("", response_model=Page[CorrespondentOut], summary="Список корреспондентов")
async def list_correspondents(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=200, description="Наименование или ФИО подписанта"),
    inn: str | None = Query(None, max_length=12),
    _: User = Depends(require_permission(Permission.CORRESPONDENT_VIEW)),
    service: CorrespondentService = Depends(get_correspondent_service),
):
    return await service.list_page(search=search, inn=inn, page=page, page_size=page_size)


@router.get("/{correspondent_id}", response_model=CorrespondentOut, summary="Карточка корреспондента")
async def get_correspondent(correspondent_id: uuid.UUID,
                            _: User = Depends(require_permission(Permission.CORRESPONDENT_VIEW)),
                            service: CorrespondentService = Depends(get_correspondent_service)):
    return await service.get(correspondent_id)


@router.patch("/{correspondent_id}", response_model=CorrespondentOut, summary="Редактировать корреспондента")
async def update_correspondent(correspondent_id: uuid.UUID, data: CorrespondentUpdate,
                               actor: User = Depends(require_permission(Permission.CORRESPONDENT_EDIT)),
                               service: CorrespondentService = Depends(get_correspondent_service)):
    return await service.update(actor, correspondent_id, data)

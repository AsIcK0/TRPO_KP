import uuid

from fastapi import APIRouter, Depends

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import get_current_user, require_permission
from app.dependencies.services import get_dictionary_service
from app.models.entities import User
from app.schemas.dictionary import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    DocumentTypeCreate,
    DocumentTypeOut,
    DocumentTypeUpdate,
    PositionCreate,
    PositionOut,
    PositionUpdate,
)
from app.security.permissions import Permission
from app.services.dictionaries import DictionaryService

_manage = require_permission(Permission.DICTIONARY_MANAGE)

departments_router = APIRouter(prefix="/departments", tags=["departments"], responses=ERROR_RESPONSES)
positions_router = APIRouter(prefix="/positions", tags=["positions"], responses=ERROR_RESPONSES)
types_router = APIRouter(prefix="/document-types", tags=["document-types"], responses=ERROR_RESPONSES)


@departments_router.get("", response_model=list[DepartmentOut], summary="Список подразделений (admin)")
async def list_departments(_: User = Depends(_manage), service: DictionaryService = Depends(get_dictionary_service)):
    return await service.list_departments()


@departments_router.post("", response_model=DepartmentOut, status_code=201, summary="Создать подразделение (admin)")
async def create_department(data: DepartmentCreate, actor: User = Depends(_manage),
                            service: DictionaryService = Depends(get_dictionary_service)):
    return await service.create_department(actor, data.name)


@departments_router.patch("/{item_id}", response_model=DepartmentOut, summary="Изменить подразделение (admin)")
async def update_department(item_id: uuid.UUID, data: DepartmentUpdate, actor: User = Depends(_manage),
                            service: DictionaryService = Depends(get_dictionary_service)):
    return await service.update_department(actor, item_id, data.model_dump(exclude_unset=True))


@positions_router.get("", response_model=list[PositionOut], summary="Список должностей (admin)")
async def list_positions(_: User = Depends(_manage), service: DictionaryService = Depends(get_dictionary_service)):
    return await service.list_positions()


@positions_router.post("", response_model=PositionOut, status_code=201, summary="Создать должность (admin)")
async def create_position(data: PositionCreate, actor: User = Depends(_manage),
                          service: DictionaryService = Depends(get_dictionary_service)):
    return await service.create_position(actor, data.name)


@positions_router.patch("/{item_id}", response_model=PositionOut, summary="Изменить должность (admin)")
async def update_position(item_id: uuid.UUID, data: PositionUpdate, actor: User = Depends(_manage),
                          service: DictionaryService = Depends(get_dictionary_service)):
    return await service.update_position(actor, item_id, data.model_dump(exclude_unset=True))


@types_router.get("", response_model=list[DocumentTypeOut], summary="Типы документов (любой авторизованный)")
async def list_document_types(_: User = Depends(get_current_user),
                              service: DictionaryService = Depends(get_dictionary_service)):
    return await service.list_types()


@types_router.post("", response_model=DocumentTypeOut, status_code=201, summary="Создать тип документа (admin)")
async def create_document_type(data: DocumentTypeCreate, actor: User = Depends(_manage),
                               service: DictionaryService = Depends(get_dictionary_service)):
    return await service.create_type(actor, data.name, data.is_active)


@types_router.patch("/{item_id}", response_model=DocumentTypeOut, summary="Изменить тип документа (admin)")
async def update_document_type(item_id: uuid.UUID, data: DocumentTypeUpdate, actor: User = Depends(_manage),
                               service: DictionaryService = Depends(get_dictionary_service)):
    return await service.update_type(actor, item_id, data.model_dump(exclude_unset=True))

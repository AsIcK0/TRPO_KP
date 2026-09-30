import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile

from app.api.v1.common import ERROR_RESPONSES
from app.core.config import get_settings
from app.dependencies.auth import require_permission
from app.dependencies.services import get_attachment_service, get_document_service, get_resolution_service
from app.models.entities import User
from app.models.enums import AttachmentType
from app.schemas.attachment import AttachmentOut
from app.schemas.common import Page
from app.schemas.document import (
    DocumentCreate,
    DocumentDetail,
    DocumentFilters,
    DocumentOut,
    DocumentUpdate,
    StatusChangeRequest,
)
from app.schemas.history import HistoryOut
from app.schemas.resolution import ResolutionCreate, ResolutionOut
from app.security.permissions import Permission
from app.services.attachments import AttachmentService
from app.services.documents import DocumentService
from app.services.resolutions import ResolutionService

router = APIRouter(prefix="/incoming", tags=["incoming"], responses=ERROR_RESPONSES)


@router.post("", response_model=DocumentDetail, status_code=201,
             summary="Регистрация карточки входящего документа (clerk)")
async def register_document(data: DocumentCreate,
                            actor: User = Depends(require_permission(Permission.DOCUMENT_REGISTER)),
                            service: DocumentService = Depends(get_document_service)):
    """Регистрационный номер и дата регистрации присваиваются автоматически (атомарно).
    Файл скана прикрепляется следующим запросом `POST /incoming/{id}/files`."""
    return await service.register(actor, data)


@router.get("", response_model=Page[DocumentOut], summary="Поиск, фильтрация и список карточек")
async def list_documents(filters: Annotated[DocumentFilters, Query()],
                         actor: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
                         service: DocumentService = Depends(get_document_service)):
    """Исполнитель видит только документы со своими резолюциями и не может использовать поиск/фильтры."""
    return await service.search(actor, filters)


@router.get("/by-registration-number/{registration_number:path}", response_model=DocumentDetail,
            summary="Карточка по регистрационному номеру")
async def get_by_number(registration_number: str,
                        actor: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
                        service: DocumentService = Depends(get_document_service)):
    return await service.get_by_number(actor, registration_number)


@router.get("/{document_id}", response_model=DocumentDetail,
            summary="Карточка документа: реквизиты, резолюции, вложения, история")
async def get_document(document_id: uuid.UUID, actor: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
                       service: DocumentService = Depends(get_document_service)):
    return await service.get_detail(actor, document_id)


@router.patch("/{document_id}", response_model=DocumentDetail,
              summary="Редактирование карточки до архивирования (clerk)")
async def update_document(document_id: uuid.UUID, data: DocumentUpdate,
                          actor: User = Depends(require_permission(Permission.DOCUMENT_EDIT)),
                          service: DocumentService = Depends(get_document_service)):
    return await service.update(actor, document_id, data)


@router.delete("/{document_id}", status_code=204, summary="Удаление карточки (только admin)")
async def delete_document(document_id: uuid.UUID,
                          actor: User = Depends(require_permission(Permission.DOCUMENT_DELETE)),
                          service: DocumentService = Depends(get_document_service)) -> Response:
    """Исключительный случай: ошибочная регистрация или дубликат. Делопроизводитель аннулирует запись
    сменой статуса, а не удалением."""
    await service.delete(actor, document_id)
    return Response(status_code=204)


@router.get("/{document_id}/history", response_model=list[HistoryOut], summary="История действий по карточке")
async def get_history(document_id: uuid.UUID, actor: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
                      service: DocumentService = Depends(get_document_service)):
    return await service.history(actor, document_id)


@router.post("/{document_id}/status", response_model=DocumentDetail,
             summary="Смена статуса карточки (с записью в историю)")
async def change_status(document_id: uuid.UUID, data: StatusChangeRequest,
                        actor: User = Depends(require_permission(Permission.STATUS_CHANGE, Permission.DOCUMENT_ANNUL,
                                                                 any_of=True)),
                        service: DocumentService = Depends(get_document_service)):
    """Допустимость перехода и роль проверяются централизованной машиной состояний; недопустимый переход — 409."""
    return await service.change_status(actor, document_id, data)


@router.post("/{document_id}/resolutions", response_model=ResolutionOut, status_code=201,
             summary="Создание резолюции (manager)")
async def create_resolution(document_id: uuid.UUID, data: ResolutionCreate,
                            actor: User = Depends(require_permission(Permission.RESOLUTION_CREATE)),
                            service: ResolutionService = Depends(get_resolution_service)):
    """При первой резолюции документ автоматически переходит «на рассмотрении» → «на исполнении»."""
    return await service.create(actor, document_id, data)


@router.get("/{document_id}/resolutions", response_model=list[ResolutionOut], summary="Резолюции по документу")
async def list_resolutions(document_id: uuid.UUID,
                           actor: User = Depends(require_permission(Permission.RESOLUTION_VIEW)),
                           service: ResolutionService = Depends(get_resolution_service)):
    return await service.list_for_document(actor, document_id)


@router.post("/{document_id}/files", response_model=AttachmentOut, status_code=201,
             summary="Прикрепление файла (PDF, JPG, PNG, DOCX) к карточке")
async def upload_file(document_id: uuid.UUID, file: UploadFile = File(description="PDF, JPG, PNG или DOCX"),
                      attachment_type: Annotated[AttachmentType | None, Form()] = None,
                      actor: User = Depends(require_permission(Permission.FILE_ATTACH)),
                      service: AttachmentService = Depends(get_attachment_service)):
    """Делопроизводитель прикрепляет скан (по умолчанию `source_scan`), исполнитель — отчетные материалы
    (`execution_report`). Размер ограничен MAX_UPLOAD_SIZE_MB."""
    data = await file.read(get_settings().max_upload_bytes + 1)  # +1 байт, чтобы обнаружить превышение лимита
    return await service.upload(actor, document_id, filename=file.filename, content_type=file.content_type,
                                data=data, attachment_type=attachment_type)

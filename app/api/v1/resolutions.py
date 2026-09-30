import uuid

from fastapi import APIRouter, Depends

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import require_permission
from app.dependencies.services import get_resolution_service
from app.models.entities import User
from app.schemas.resolution import ResolutionOut, ResolutionUpdate
from app.security.permissions import Permission
from app.services.resolutions import ResolutionService

router = APIRouter(prefix="/resolutions", tags=["resolutions"], responses=ERROR_RESPONSES)


@router.patch("/{resolution_id}", response_model=ResolutionOut,
              summary="Редактирование резолюции до завершения процесса (manager)")
async def update_resolution(resolution_id: uuid.UUID, data: ResolutionUpdate,
                            actor: User = Depends(require_permission(Permission.RESOLUTION_EDIT)),
                            service: ResolutionService = Depends(get_resolution_service)):
    return await service.update(actor, resolution_id, data)

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import require_permission
from app.dependencies.services import get_attachment_service, get_storage_dep
from app.models.entities import User
from app.security.permissions import Permission
from app.services.attachments import AttachmentService
from app.storage.s3 import S3Storage

router = APIRouter(prefix="/files", tags=["files"], responses=ERROR_RESPONSES)


def content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "").strip() or "file"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/{attachment_id}/download", summary="Скачивание файла (после проверки прав доступа)",
            response_class=StreamingResponse)
async def download_file(attachment_id: uuid.UUID,
                        actor: User = Depends(require_permission(Permission.DOCUMENT_VIEW)),
                        service: AttachmentService = Depends(get_attachment_service),
                        storage: S3Storage = Depends(get_storage_dep)) -> StreamingResponse:
    attachment = await service.get_for_download(actor, attachment_id)
    headers = {"Content-Disposition": content_disposition(attachment.original_filename),
               "Content-Length": str(attachment.size_bytes)}
    return StreamingResponse(storage.stream(attachment.storage_key), media_type=attachment.content_type,
                             headers=headers)

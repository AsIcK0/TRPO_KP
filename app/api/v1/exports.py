from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import require_permission
from app.dependencies.services import get_export_service
from app.exports.csv_export import iter_csv
from app.models.entities import User
from app.schemas.report import RegistrationLogQuery
from app.security.permissions import Permission
from app.services.exports import ExportService

router = APIRouter(prefix="/exports", tags=["exports"], responses=ERROR_RESPONSES)


@router.get("/registration-log", summary="Выгрузка журнала регистрации в CSV (clerk)",
            response_class=StreamingResponse,
            responses={200: {"content": {"text/csv": {}}, "description": "CSV: UTF-8 с BOM, разделитель «;»"}})
async def export_registration_log(query: Annotated[RegistrationLogQuery, Query()],
                                  actor: User = Depends(require_permission(Permission.EXPORT_REGISTRY)),
                                  service: ExportService = Depends(get_export_service)) -> StreamingResponse:
    headers, rows = await service.registration_log(actor, query)
    filename = f"registration-log-{date.today().isoformat()}.csv"
    return StreamingResponse(iter_csv(headers, rows), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})

from fastapi import APIRouter, Depends, Response

from app.api.v1.common import ERROR_RESPONSES
from app.dependencies.auth import require_permission
from app.dependencies.services import get_report_service
from app.models.entities import User
from app.schemas.report import ReportRequest
from app.security.permissions import Permission
from app.services.reports import ReportService

router = APIRouter(prefix="/reports", tags=["reports"], responses=ERROR_RESPONSES)


@router.post("/generate", summary="Сформировать PDF-отчет (clerk, manager)", response_class=Response,
             responses={200: {"content": {"application/pdf": {}}, "description": "PDF-файл отчета"}})
async def generate_report(data: ReportRequest, actor: User = Depends(require_permission(Permission.REPORT_GENERATE)),
                          service: ReportService = Depends(get_report_service)) -> Response:
    """Типы: `documents` (по документам), `executors` (по исполнителям), `deadlines` (по срокам исполнения).
    Период отбирается по дате регистрации документов."""
    pdf, filename = await service.generate(actor, data)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

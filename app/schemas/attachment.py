import uuid
from datetime import datetime

from app.models.enums import AttachmentType
from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


class AttachmentOut(ORMModel):
    id: uuid.UUID
    document_id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    attachment_type: AttachmentType
    uploaded_by: uuid.UUID
    uploader: UserBrief
    created_at: datetime

"""Фабрики сервисов для внедрения в роутеры (одна сессия БД на запрос)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.dependencies.db import get_db
from app.services.attachments import AttachmentService
from app.services.auth import AuthService
from app.services.correspondents import CorrespondentService
from app.services.dictionaries import DictionaryService
from app.services.documents import DocumentService
from app.services.exports import ExportService
from app.services.reports import ReportService
from app.services.resolutions import ResolutionService
from app.services.users import UserService
from app.storage.s3 import S3Storage, get_storage


def get_storage_dep() -> S3Storage:
    return get_storage()


def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db, get_settings())


def get_user_service(db: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(db)


def get_dictionary_service(db: AsyncSession = Depends(get_db)) -> DictionaryService:
    return DictionaryService(db)


def get_correspondent_service(db: AsyncSession = Depends(get_db)) -> CorrespondentService:
    return CorrespondentService(db)


def get_document_service(db: AsyncSession = Depends(get_db),
                         storage: S3Storage = Depends(get_storage_dep)) -> DocumentService:
    return DocumentService(db, get_settings(), storage)


def get_resolution_service(db: AsyncSession = Depends(get_db)) -> ResolutionService:
    return ResolutionService(db)


def get_attachment_service(db: AsyncSession = Depends(get_db),
                           storage: S3Storage = Depends(get_storage_dep)) -> AttachmentService:
    return AttachmentService(db, get_settings(), storage)


def get_report_service(db: AsyncSession = Depends(get_db)) -> ReportService:
    return ReportService(db, get_settings())


def get_export_service(db: AsyncSession = Depends(get_db)) -> ExportService:
    return ExportService(db, get_settings())

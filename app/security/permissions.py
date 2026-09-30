"""Матрица разрешений — единый источник истины для RBAC (backend)."""

from enum import StrEnum

from app.models.enums import Role


class Permission(StrEnum):
    AUTHENTICATE = "auth:login"
    USER_CREATE = "user:create"
    USER_VIEW = "user:view"
    USER_EDIT = "user:edit"
    USER_DEACTIVATE = "user:deactivate"
    DICTIONARY_MANAGE = "dictionary:manage"  # подразделения, должности, типы документов
    CORRESPONDENT_CREATE = "correspondent:create"
    CORRESPONDENT_EDIT = "correspondent:edit"
    CORRESPONDENT_VIEW = "correspondent:view"
    DOCUMENT_REGISTER = "document:register"
    DOCUMENT_EDIT = "document:edit"
    DOCUMENT_VIEW = "document:view"
    DOCUMENT_SEARCH = "document:search"
    DOCUMENT_DELETE = "document:delete"
    DOCUMENT_ANNUL = "document:annul"  # аннулирование (возврат в «зарегистрирован»)
    RESOLUTION_CREATE = "resolution:create"
    RESOLUTION_EDIT = "resolution:edit"
    RESOLUTION_VIEW = "resolution:view"
    FILE_ATTACH = "file:attach"
    STATUS_CHANGE = "document:change_status"
    REPORT_GENERATE = "report:generate"
    EXPORT_REGISTRY = "export:registry"


P = Permission

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.CLERK: frozenset({
        P.AUTHENTICATE,
        P.CORRESPONDENT_CREATE, P.CORRESPONDENT_EDIT, P.CORRESPONDENT_VIEW,
        P.DOCUMENT_REGISTER, P.DOCUMENT_EDIT, P.DOCUMENT_VIEW, P.DOCUMENT_SEARCH,
        P.RESOLUTION_VIEW, P.FILE_ATTACH, P.STATUS_CHANGE,
        P.REPORT_GENERATE, P.EXPORT_REGISTRY,
    }),
    Role.MANAGER: frozenset({
        P.AUTHENTICATE,
        P.DOCUMENT_VIEW, P.DOCUMENT_SEARCH,
        P.RESOLUTION_CREATE, P.RESOLUTION_EDIT, P.RESOLUTION_VIEW,
        P.REPORT_GENERATE,
    }),
    Role.EXECUTOR: frozenset({
        P.AUTHENTICATE,
        P.DOCUMENT_VIEW, P.RESOLUTION_VIEW, P.STATUS_CHANGE, P.FILE_ATTACH,
    }),
    Role.ADMIN: frozenset({
        P.AUTHENTICATE,
        P.USER_CREATE, P.USER_VIEW, P.USER_EDIT, P.USER_DEACTIVATE,
        P.DICTIONARY_MANAGE,
        P.DOCUMENT_DELETE, P.DOCUMENT_ANNUL,
        # только чтение карточек: чтобы убедиться, что удаляется именно дубликат/ошибочная запись
        # (GET /incoming по ТЗ доступен всем ролям). Поиск и фильтрация администратору недоступны.
        P.DOCUMENT_VIEW,
    }),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_of(role: Role) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS.get(role, frozenset()))

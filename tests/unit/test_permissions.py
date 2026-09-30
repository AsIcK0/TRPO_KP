import pytest

from app.models.enums import Role
from app.security.permissions import ROLE_PERMISSIONS, Permission, has_permission, permissions_of

P = Permission


@pytest.mark.parametrize(("role", "allowed"), [
    (Role.CLERK, [P.DOCUMENT_REGISTER, P.DOCUMENT_EDIT, P.DOCUMENT_SEARCH, P.STATUS_CHANGE, P.EXPORT_REGISTRY,
                  P.REPORT_GENERATE, P.FILE_ATTACH, P.CORRESPONDENT_CREATE]),
    (Role.MANAGER, [P.RESOLUTION_CREATE, P.RESOLUTION_EDIT, P.DOCUMENT_SEARCH, P.REPORT_GENERATE]),
    (Role.EXECUTOR, [P.DOCUMENT_VIEW, P.RESOLUTION_VIEW, P.STATUS_CHANGE, P.FILE_ATTACH]),
    (Role.ADMIN, [P.USER_CREATE, P.USER_VIEW, P.USER_EDIT, P.USER_DEACTIVATE, P.DOCUMENT_DELETE]),
])
def test_role_has_its_permissions(role, allowed):
    assert all(has_permission(role, p) for p in allowed)


@pytest.mark.parametrize(("role", "denied"), [
    (Role.CLERK, [P.DOCUMENT_DELETE, P.RESOLUTION_CREATE, P.USER_CREATE]),
    (Role.MANAGER, [P.DOCUMENT_REGISTER, P.STATUS_CHANGE, P.FILE_ATTACH, P.EXPORT_REGISTRY, P.DOCUMENT_DELETE]),
    (Role.EXECUTOR, [P.DOCUMENT_SEARCH, P.DOCUMENT_REGISTER, P.RESOLUTION_CREATE, P.REPORT_GENERATE,
                     P.DOCUMENT_DELETE, P.EXPORT_REGISTRY]),
    (Role.ADMIN, [P.DOCUMENT_REGISTER, P.DOCUMENT_EDIT, P.DOCUMENT_SEARCH, P.RESOLUTION_CREATE,
                  P.FILE_ATTACH, P.STATUS_CHANGE, P.REPORT_GENERATE, P.EXPORT_REGISTRY]),
])
def test_role_lacks_foreign_permissions(role, denied):
    assert not any(has_permission(role, p) for p in denied)


def test_only_admin_can_delete_documents():
    assert [r for r in Role if has_permission(r, P.DOCUMENT_DELETE)] == [Role.ADMIN]


def test_every_role_can_authenticate_and_is_configured():
    assert set(ROLE_PERMISSIONS) == set(Role)
    assert all(has_permission(r, P.AUTHENTICATE) for r in Role)
    assert permissions_of(Role.EXECUTOR) == sorted(permissions_of(Role.EXECUTOR))

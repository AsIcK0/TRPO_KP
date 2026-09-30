import pytest

from app.models.enums import DocumentStatus as S
from app.models.enums import Role
from app.services.workflow import allowed_targets, is_transition_allowed, transition_roles

LIFECYCLE = [
    (S.REGISTERED, S.UNDER_REVIEW, Role.CLERK),
    (S.UNDER_REVIEW, S.IN_EXECUTION, Role.MANAGER),
    (S.IN_EXECUTION, S.EXECUTED, Role.EXECUTOR),
    (S.EXECUTED, S.REMOVED_FROM_CONTROL, Role.CLERK),
    (S.REMOVED_FROM_CONTROL, S.ARCHIVED, Role.CLERK),
]


@pytest.mark.parametrize(("old", "new", "role"), LIFECYCLE)
def test_base_lifecycle_transitions(old, new, role):
    assert is_transition_allowed(old, new)
    assert transition_roles(old, new) == {role}


@pytest.mark.parametrize(("old", "new"), [
    (S.REGISTERED, S.EXECUTED), (S.REGISTERED, S.ARCHIVED), (S.UNDER_REVIEW, S.EXECUTED),
    (S.EXECUTED, S.IN_EXECUTION), (S.ARCHIVED, S.EXECUTED), (S.IN_EXECUTION, S.UNDER_REVIEW),
    (S.REGISTERED, S.REGISTERED),
])
def test_forbidden_transitions(old, new):
    assert not is_transition_allowed(old, new)


@pytest.mark.parametrize("status", [s for s in S if s is not S.REGISTERED])
def test_annulment_from_any_status_only_for_admin(status):
    assert transition_roles(status, S.REGISTERED) == {Role.ADMIN}


def test_registered_has_single_forward_target():
    assert allowed_targets(S.REGISTERED) == [S.UNDER_REVIEW]

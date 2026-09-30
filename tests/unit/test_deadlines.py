from datetime import date, timedelta

import pytest

from app.models.enums import DocumentStatus as S
from app.services.deadlines import DeadlineState, days_left, deadline_state

TODAY = date(2026, 9, 30)


@pytest.mark.parametrize(("offset", "status", "expected"), [
    (-1, S.IN_EXECUTION, DeadlineState.OVERDUE),
    (-30, S.UNDER_REVIEW, DeadlineState.OVERDUE),
    (0, S.IN_EXECUTION, DeadlineState.WARNING),
    (3, S.IN_EXECUTION, DeadlineState.WARNING),
    (4, S.IN_EXECUTION, DeadlineState.OK),
    (-5, S.EXECUTED, DeadlineState.CLOSED),
    (-5, S.ARCHIVED, DeadlineState.CLOSED),
    (-5, S.REMOVED_FROM_CONTROL, DeadlineState.CLOSED),
])
def test_deadline_state(offset, status, expected):
    assert deadline_state(TODAY + timedelta(days=offset), status, TODAY, warning_days=3) == expected


def test_days_left_negative_when_overdue():
    assert days_left(TODAY - timedelta(days=2), TODAY) == -2
    assert days_left(TODAY + timedelta(days=5), TODAY) == 5

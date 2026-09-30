import pytest

from app.services.reg_number import counter_key, format_registration_number, validate_template


def test_default_template_format():
    assert format_registration_number("ВХ-{YYYY}-{NNNNNN}", 2026, 1) == "ВХ-2026-000001"


def test_number_wider_than_mask_is_not_truncated():
    assert format_registration_number("ВХ-{YYYY}-{NNN}", 2026, 12345) == "ВХ-2026-12345"


def test_short_year_and_custom_template():
    assert format_registration_number("IN/{YY}/{NNNN}", 2026, 7) == "IN/26/0007"


def test_counter_resets_yearly_only_if_template_has_year():
    assert counter_key("ВХ-{YYYY}-{NNNNNN}", 2026) == 2026
    assert counter_key("ВХ-{NNNNNN}", 2026) == 0  # сквозная нумерация — иначе коллизии при смене года


def test_template_without_sequence_is_rejected():
    with pytest.raises(ValueError):
        validate_template("ВХ-{YYYY}")

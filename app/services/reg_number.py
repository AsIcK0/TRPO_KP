"""Формирование регистрационного номера по шаблону REG_NUMBER_TEMPLATE.

Поддерживаемые плейсхолдеры: {YYYY}, {YY}, {N...} (число N задает ширину с ведущими нулями).
Пример: «ВХ-{YYYY}-{NNNNNN}» -> «ВХ-2026-000001».
"""

import re

_PLACEHOLDER = re.compile(r"\{(YYYY|YY|N+)\}")
_SEQUENCE = re.compile(r"\{N+\}")


def validate_template(template: str) -> str:
    if not _SEQUENCE.search(template):
        raise ValueError("REG_NUMBER_TEMPLATE должен содержать порядковый номер вида {NNNNNN}")
    return template


def uses_year(template: str) -> bool:
    return "{YYYY}" in template or "{YY}" in template


def counter_key(template: str, year: int) -> int:
    """Ключ счетчика: годовой сброс, если в шаблоне есть год; иначе сквозная нумерация (ключ 0)."""
    return year if uses_year(template) else 0


def format_registration_number(template: str, year: int, sequence: int) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "YYYY":
            return f"{year:04d}"
        if token == "YY":
            return f"{year % 100:02d}"
        return str(sequence).zfill(len(token))

    return _PLACEHOLDER.sub(replace, template)

"""ER-диаграмма в docs/data-schema.md должна содержать все таблицы и столбцы ORM-моделей."""

import re
from pathlib import Path

from app.db.base import Base
from app.models import entities  # noqa: F401  — регистрирует модели в metadata

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_er_diagram_matches_orm_models():
    text = (DOCS / "data-schema.md").read_text(encoding="utf-8")
    block = next(b for b in re.findall(r"```mermaid\n(.*?)```", text, flags=re.S) if "erDiagram" in b)
    entities_in_doc = {name: body for name, body in re.findall(r"^\s*(\w+)\s*\{(.*?)\}", block, flags=re.S | re.M)}
    for table in Base.metadata.sorted_tables:
        assert table.name in entities_in_doc, f"нет сущности {table.name} на ER-диаграмме"
        doc_columns = {line.split()[1] for line in entities_in_doc[table.name].strip().splitlines() if line.strip()}
        assert {c.name for c in table.columns} == doc_columns, table.name

"""Диаграмма состояний в docs/ должна совпадать с машиной состояний в коде."""

import re
from pathlib import Path

from app.models.enums import DocumentStatus
from app.services.workflow import TRANSITIONS

DOCS = Path(__file__).resolve().parents[2] / "docs"


def _mermaid_blocks(text: str) -> list[str]:
    return re.findall(r"```mermaid\n(.*?)```", text, flags=re.S)


def test_state_diagram_matches_transition_matrix():
    block = next(b for b in _mermaid_blocks((DOCS / "state-diagram.md").read_text(encoding="utf-8"))
                 if "stateDiagram" in b)
    aliases = dict(re.findall(r'state "([^"]+)" as (\w+)', block))
    ids = {alias: DocumentStatus(label) for label, alias in aliases.items()}
    assert set(ids.values()) == set(DocumentStatus)

    drawn = set()
    for old, new, roles in re.findall(r"^\s*(\w+)\s*-->\s*(\w+)\s*:\s*(.+)$", block, flags=re.M):
        if old == "[*]" or old not in ids:
            continue
        drawn.add((ids[old], ids[new], frozenset(r.strip() for r in roles.split(","))))
    expected = {(o, n, frozenset(r.value for r in roles)) for (o, n), roles in TRANSITIONS.items()}
    assert drawn == expected

"""CSV-выгрузка: UTF-8 with BOM, разделитель «;», защита от CSV-инъекций (формулы в Excel)."""

import csv
import io
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

BOM = "\ufeff"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def iter_csv(headers: Sequence[str], rows: Iterable[Sequence[Any]], chunk_rows: int = 500) -> Iterator[bytes]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

    def flush() -> bytes:
        data = buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
        return data

    writer.writerow(headers)
    yield BOM.encode("utf-8") + flush()
    count = 0
    for row in rows:
        writer.writerow([_cell(v) for v in row])
        count += 1
        if count % chunk_rows == 0:
            yield flush()
    tail = flush()
    if tail:
        yield tail

from app.exports.csv_export import iter_csv


def _render(headers, rows) -> bytes:
    return b"".join(iter_csv(headers, rows))


def test_utf8_bom_semicolon_and_cyrillic():
    raw = _render(["Номер", "Корреспондент"], [["ВХ-2026-000001", "ООО «Ромашка»"]])
    assert raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == "Номер;Корреспондент"
    assert lines[1] == "ВХ-2026-000001;ООО «Ромашка»"


def test_delimiters_and_quotes_inside_values_are_escaped():
    text = _render(["a", "b"], [["x;y", 'say "hi"']]).decode("utf-8-sig")
    assert '"x;y"' in text and '"say ""hi"""' in text


def test_formula_injection_is_neutralised():
    text = _render(["a"], [["=1+1"], ["@SUM(A1)"], ["+7 495"], ["обычный текст"]]).decode("utf-8-sig")
    assert "'=1+1" in text and "'@SUM(A1)" in text and "'+7 495" in text and "'обычный" not in text


def test_large_export_is_chunked_and_complete():
    rows = [[f"ВХ-{i:06d}", i] for i in range(1200)]
    chunks = list(iter_csv(["n", "i"], rows, chunk_rows=500))
    assert len(chunks) >= 3
    assert len(b"".join(chunks).decode("utf-8-sig").splitlines()) == 1201

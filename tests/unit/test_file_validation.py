import pytest

from app.core.errors import AppError, DomainValidationError, PayloadTooLargeError
from app.storage.validation import DOCX_MIME, sanitize_filename, validate_upload

LIMIT = 1024


def test_valid_pdf_keeps_cyrillic_display_name():
    result = validate_upload("Скан письма.PDF", "application/pdf", b"%PDF-1.7 body", LIMIT)
    assert (result.extension, result.filename) == (".pdf", "Скан письма.PDF")


@pytest.mark.parametrize(("name", "mime", "data", "ext"), [
    ("a.jpg", "image/jpeg", b"\xff\xd8\xff\xe0data", ".jpg"),
    ("a.jpeg", "image/jpeg", b"\xff\xd8\xff\xe0data", ".jpg"),
    ("a.png", "image/png", b"\x89PNG\r\n\x1a\nxx", ".png"),
    ("a.docx", DOCX_MIME, b"PK\x03\x04xx", ".docx"),
])
def test_all_allowed_formats(name, mime, data, ext):
    assert validate_upload(name, mime, data, LIMIT).extension == ext


@pytest.mark.parametrize(("name", "mime", "data", "code"), [
    ("virus.exe", "application/octet-stream", b"MZ", "UNSUPPORTED_FILE_TYPE"),
    ("a.pdf", "image/png", b"%PDF", "UNSUPPORTED_FILE_TYPE"),
    ("a.pdf", "application/pdf", b"MZ\x90\x00", "FILE_CONTENT_MISMATCH"),
    ("a.pdf", "application/pdf", b"", "EMPTY_FILE"),
    ("noext", "application/pdf", b"%PDF", "UNSUPPORTED_FILE_TYPE"),
])
def test_rejected_files(name, mime, data, code):
    with pytest.raises(DomainValidationError) as exc:
        validate_upload(name, mime, data, LIMIT)
    assert exc.value.code == code


def test_size_limit():
    with pytest.raises(PayloadTooLargeError):
        validate_upload("a.pdf", "application/pdf", b"%PDF" + b"0" * LIMIT, LIMIT)


def test_path_traversal_is_stripped():
    assert sanitize_filename("../../etc/passwd.pdf") == "passwd.pdf"
    assert sanitize_filename("..\\..\\windows\\a.pdf") == "a.pdf"
    with pytest.raises(AppError):
        validate_upload("../", "application/pdf", b"%PDF", LIMIT)

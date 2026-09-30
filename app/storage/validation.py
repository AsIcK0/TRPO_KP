"""Проверка загружаемых файлов: размер, расширение, MIME-тип и сигнатура содержимого."""

import re
from dataclasses import dataclass

from app.core.errors import DomainValidationError, PayloadTooLargeError

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# расширение -> (допустимые MIME клиента, канонический MIME, сигнатура начала файла)
ALLOWED_TYPES: dict[str, tuple[frozenset[str], str, bytes]] = {
    ".pdf": (frozenset({"application/pdf"}), "application/pdf", b"%PDF"),
    ".jpg": (frozenset({"image/jpeg", "image/jpg", "image/pjpeg"}), "image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": (frozenset({"image/jpeg", "image/jpg", "image/pjpeg"}), "image/jpeg", b"\xff\xd8\xff"),
    ".png": (frozenset({"image/png"}), "image/png", b"\x89PNG\r\n\x1a\n"),
    ".docx": (frozenset({DOCX_MIME}), DOCX_MIME, b"PK\x03\x04"),
}
ALLOWED_HUMAN = "PDF, JPG, PNG, DOCX"


@dataclass(frozen=True)
class ValidatedFile:
    filename: str      # безопасное исходное имя (только для отображения, не для путей)
    extension: str     # нормализованное расширение для storage_key
    content_type: str  # канонический MIME
    size: int


def sanitize_filename(name: str | None) -> str:
    """Оставляет только базовое имя: отбрасывает каталоги (в т.ч. «..\\..\\») и управляющие символы."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    return base[:255]


def validate_upload(filename: str | None, content_type: str | None, data: bytes, max_bytes: int) -> ValidatedFile:
    safe_name = sanitize_filename(filename)
    if not safe_name:
        raise DomainValidationError("Не указано имя файла", code="INVALID_FILENAME", field="file")
    if not data:
        raise DomainValidationError("Файл пустой", code="EMPTY_FILE", field="file")
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"Размер файла превышает {max_bytes // (1024 * 1024)} МБ", field="file")

    ext = "." + safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if ext not in ALLOWED_TYPES:
        raise DomainValidationError(f"Недопустимое расширение файла. Разрешены: {ALLOWED_HUMAN}",
                                    code="UNSUPPORTED_FILE_TYPE", field="file")
    mimes, canonical, signature = ALLOWED_TYPES[ext]
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime not in mimes:
        raise DomainValidationError(f"Недопустимый MIME-тип файла. Разрешены: {ALLOWED_HUMAN}",
                                    code="UNSUPPORTED_FILE_TYPE", field="file")
    if not data.startswith(signature):
        raise DomainValidationError("Содержимое файла не соответствует его расширению",
                                    code="FILE_CONTENT_MISMATCH", field="file")
    return ValidatedFile(safe_name, ".jpg" if ext == ".jpeg" else ext, canonical, len(data))
